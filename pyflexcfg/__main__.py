import os
import re
import sys
from pathlib import Path

from pyflexcfg.components.encryption import AESCipher

# YAML scalar forms \S+ cannot capture whole — quoted strings, block scalars, anchors.
_UNSAFE_SCALAR_STARTS = frozenset('"\'|>&*')


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
        dry_run = '--dry-run' in sys.argv[2:]
        _cmd_encrypt(dry_run=dry_run)
    else:
        print(
            f'Unknown command: {cmd!r}. Available: show, env, encrypt [--dry-run]',
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_encrypt(*, dry_run: bool) -> None:
    _key_env = 'PYFLEX_CFG_KEY'
    _root_env = 'PYFLEX_CFG_ROOT_PATH'

    config_root_str = os.getenv(_root_env)
    config_root = Path(config_root_str) if config_root_str else Path.cwd() / 'config'

    key = os.getenv(_key_env)
    if not key:
        print(f'Error: {_key_env} is not set.', file=sys.stderr)
        sys.exit(1)

    cipher = AESCipher(key)
    legacy_found = []
    plaintext_found = []
    unresolved = []

    yaml_files = sorted(config_root.rglob('*.yaml')) + sorted(config_root.rglob('*.yml'))
    for yaml_file in yaml_files:
        text = yaml_file.read_text(encoding='utf-8')
        lines = text.splitlines(keepends=True)
        new_lines = []
        file_changed = False

        for line in lines:
            if line.lstrip().startswith('#'):
                new_lines.append(line)
                continue

            def replace_fn(m: re.Match, _line=line, _file=yaml_file) -> str:
                nonlocal file_changed
                tag, value = m.group(1), m.group(2)

                if AESCipher.is_encrypted(value):
                    return m.group(0)

                rel = _file.relative_to(config_root)
                yaml_key = _line[: m.start()].strip().rstrip(':').strip()
                where = f'{rel}: {tag} key "{yaml_key}"'

                if value[0] in _UNSAFE_SCALAR_STARTS:
                    unresolved.append(f'{where} has an unsupported scalar form — encrypt manually')
                    return m.group(0)

                plaintext = value
                if AESCipher.is_legacy(value):
                    try:
                        plaintext = cipher.decrypt_legacy(value)
                    except ValueError:
                        # Either a legacy ciphertext under another key or base64-looking plaintext.
                        unresolved.append(
                            f'{where} looks like a legacy ciphertext but does not decrypt with {_key_env}'
                        )
                        return m.group(0)
                    legacy_found.append(f'{where} is a legacy AES-CBC ciphertext')
                else:
                    plaintext_found.append(f'{where} is plaintext')

                if dry_run:
                    return m.group(0)

                encrypted = cipher.encrypt_kdf(plaintext) if '_kdf' in tag else cipher.encrypt(plaintext)
                file_changed = True

                return f'{tag} {encrypted}'

            new_lines.append(re.sub(r'(!encr(?:_kdf)?)\s+(\S+)', replace_fn, line))

        if file_changed:
            yaml_file.write_text(''.join(new_lines), encoding='utf-8')
            print(f'Updated: {yaml_file.relative_to(config_root)}')

    for msg in legacy_found:
        print(msg)
    for msg in plaintext_found:
        print(msg, file=sys.stderr if dry_run else sys.stdout)
    for msg in unresolved:
        print(f'Warning: {msg}', file=sys.stderr)

    if unresolved or (dry_run and plaintext_found):
        sys.exit(1)
    if dry_run and not legacy_found:
        print('All !encr / !encr_kdf values are already encrypted.')


if __name__ == '__main__':
    main()
