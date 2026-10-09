import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import yaml

from pyflexcfg.components.encryption import AESCipher
from pyflexcfg.components.metaclasses import HandlerMeta

_BLOCK_STYLES = ('|', '>')
_ENCR_TAGS = {('!', 'encr'), ('!', 'encr_kdf')}
_KEY_ENV = 'PYFLEX_CFG_KEY'
_ROOT_ENV = 'PYFLEX_CFG_ROOT_PATH'


@dataclass
class _Report:
    legacy: list[str] = field(default_factory=list)
    plaintext: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    weak: list[str] = field(default_factory=list)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'

    if cmd == 'show':
        from pyflexcfg import Cfg

        print(str(Cfg))
    elif cmd == 'env':
        from pyflexcfg import Cfg

        print(f'config_root : {Cfg.config_root}')
        print(f'project_root: {Cfg.project_root}')
        print(f'PYFLEX_ENV  : {os.getenv("PYFLEX_ENV", "(not set)")}')
    elif cmd == 'encrypt':
        args = sys.argv[2:]
        if unknown := [arg for arg in args if arg != '--dry-run']:
            print(f'Unknown encrypt argument(s): {unknown}. Usage: pyflexcfg encrypt [--dry-run]', file=sys.stderr)
            sys.exit(1)
        _cmd_encrypt(dry_run='--dry-run' in args)
    else:
        print(
            f'Unknown command: {cmd!r}. Available: show, env, encrypt [--dry-run]',
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_encrypt(*, dry_run: bool) -> None:
    config_root_str = os.getenv(_ROOT_ENV)
    config_root = Path(config_root_str) if config_root_str else Path.cwd() / 'config'
    if not config_root.is_dir():
        print(f'Error: config root {config_root} is not a directory.', file=sys.stderr)
        sys.exit(1)

    try:
        HandlerMeta.load_env_files(config_root)
    except RuntimeError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)

    key = os.getenv(_KEY_ENV)

    if not key:
        print(f'Error: {_KEY_ENV} is not set.', file=sys.stderr)
        sys.exit(1)

    cipher = AESCipher(key)
    report = _Report()

    yaml_files = sorted(config_root.rglob('*.yaml')) + sorted(config_root.rglob('*.yml'))
    if not yaml_files:
        print(f'Error: no YAML files found under config root {config_root}.', file=sys.stderr)
        sys.exit(1)

    for yaml_file in yaml_files:
        rel = yaml_file.relative_to(config_root)
        # newline='' keeps the file's own line endings intact on read and on write.
        with yaml_file.open(encoding='utf-8', newline='') as stream:
            text = stream.read()

        edits = _find_edits(text, str(rel), cipher, report)
        if dry_run or not edits:
            continue

        for start, end, tag, plaintext in reversed(edits):
            encrypted = cipher.encrypt_kdf(plaintext) if tag == '!encr_kdf' else cipher.encrypt(plaintext)
            text = f'{text[:start]}{tag} {encrypted}{text[end:]}'
        with yaml_file.open('w', encoding='utf-8', newline='') as stream:
            stream.write(text)
        print(f'Updated: {rel}')

    for msg in report.legacy:
        print(msg)
    for msg in report.plaintext + report.weak:
        print(msg, file=sys.stderr if dry_run else sys.stdout)
    for msg in report.unresolved:
        print(f'Warning: {msg}', file=sys.stderr)

    if report.unresolved or (dry_run and (report.plaintext or report.weak)):
        sys.exit(1)
    if dry_run and not report.legacy:
        print('All !encr / !encr_kdf values are already encrypted.')


def _decrypt_or_report(
    decrypt: Callable[[str], str],
    value: str,
    report: _Report,
    *,
    found: tuple[list[str], str],
    failed: str,
) -> str | None:
    """Decrypt `value`; record `found` on success, or `failed` as unresolved and return `None`."""
    try:
        plaintext = decrypt(value)
    except ValueError:
        report.unresolved.append(failed)
        return None

    bucket, message = found
    bucket.append(message)

    return plaintext


def _find_edits(text: str, rel: str, cipher: AESCipher, report: _Report) -> list[tuple[int, int, str, str]]:
    """
    Locate `!encr` / `!encr_kdf` tagged scalars in `text` that need (re-)encrypting.

    Works on YAML tokens, so tag-like text inside strings and comments is ignored.

    Returns:
        `(start, end, tag, plaintext)` per value: its character span and what to encrypt.
    """
    try:
        tokens = list(yaml.scan(text, Loader=yaml.Loader))
    except yaml.YAMLError as exc:
        # Only the position is reported: PyYAML's own message quotes the offending line.
        mark = getattr(exc, 'problem_mark', None)
        position = f':{mark.line + 1}' if mark else ''
        report.unresolved.append(f'{rel}{position} cannot be parsed as YAML — file skipped')
        return []

    edits = []
    yaml_key = None

    for token, following in pairwise(tokens):
        if isinstance(token, yaml.KeyToken) and isinstance(following, yaml.ScalarToken):
            yaml_key = following.value

        if not isinstance(token, yaml.TagToken) or token.value not in _ENCR_TAGS:
            continue

        tag = f'!{token.value[1]}'
        target = f'key "{yaml_key}"' if yaml_key is not None else 'value'
        where = f'{rel}:{token.start_mark.line + 1}: {tag} {target}'

        if not isinstance(following, yaml.ScalarToken) or following.style in _BLOCK_STYLES:
            report.unresolved.append(f'{where} is not a plain or quoted scalar — encrypt manually')
            continue

        plaintext = _plaintext_to_encrypt(tag, following.value, where, cipher, report)
        if plaintext is not None:
            edits.append((token.start_mark.index, following.end_mark.index, tag, plaintext))

    return edits


def _plaintext_to_encrypt(tag: str, value: str, where: str, cipher: AESCipher, report: _Report) -> str | None:
    """Classify a tagged value; return its plaintext if it must be (re-)encrypted, else `None`."""
    if AESCipher.is_encrypted(value):
        # A KDF ciphertext under `!encr` is stronger than asked for and is left alone.
        if tag != '!encr_kdf' or AESCipher.is_kdf(value):
            return None
        return _decrypt_or_report(
            cipher.decrypt,
            value,
            report,
            found=(report.weak, f'{where} is encrypted without the PBKDF2 its tag requires'),
            failed=f'{where} is encrypted without PBKDF2 and does not decrypt with {_KEY_ENV}',
        )

    if AESCipher.has_marker(value):
        # Not a complete, known ciphertext, yet clearly not plaintext either: encrypting it would bury it.
        report.unresolved.append(f'{where} carries the PFLX marker but is truncated or of an unknown version')
        return None

    if AESCipher.is_legacy(value):
        # A failure here means a legacy ciphertext under another key, or base64-looking plaintext.
        return _decrypt_or_report(
            cipher.decrypt_legacy,
            value,
            report,
            found=(report.legacy, f'{where} is a legacy AES-CBC ciphertext'),
            failed=f'{where} looks like a legacy ciphertext but does not decrypt with {_KEY_ENV}',
        )

    report.plaintext.append(f'{where} is plaintext')
    return value


if __name__ == '__main__':
    main()
