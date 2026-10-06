import base64
import os
import re
import sys
from pathlib import Path


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
    # Use string literals for env var names to avoid importing pyflexcfg (which would try
    # to decrypt the very plaintext values this command is meant to encrypt).
    _key_env = 'PYFLEX_CFG_KEY'
    _root_env = 'PYFLEX_CFG_ROOT_PATH'

    config_root_str = os.getenv(_root_env)
    config_root = Path(config_root_str) if config_root_str else Path.cwd() / 'config'

    key = os.getenv(_key_env)
    if not key:
        print(f'Error: {_key_env} is not set.', file=sys.stderr)
        sys.exit(1)
    plaintext_found: list[str] = []

    yaml_files = sorted(config_root.rglob('*.yaml')) + sorted(config_root.rglob('*.yml'))
    for yaml_file in yaml_files:
        text = yaml_file.read_text(encoding='utf-8')
        lines = text.splitlines(keepends=True)
        new_lines: list[str] = []
        file_changed = False

        for line in lines:
            if line.lstrip().startswith('#'):
                new_lines.append(line)
                continue

            def replace_fn(m: re.Match, _line=line, _file=yaml_file) -> str:
                nonlocal file_changed
                tag, value = m.group(1), m.group(2)
                if _is_encrypted(value):
                    return m.group(0)
                rel = _file.relative_to(config_root)
                plaintext_found.append(f'{rel}: {tag} value for "{m.group(0).split(":")[0].strip()}" is plaintext')
                if dry_run:
                    return m.group(0)
                encrypted = _encrypt_kdf(key, value) if '_kdf' in tag else _encrypt_fast(key, value)
                file_changed = True
                return f'{tag} {encrypted}'

            new_lines.append(re.sub(r'(!encr(?:_kdf)?)\s+(\S+)', replace_fn, line))

        if file_changed:
            yaml_file.write_text(''.join(new_lines), encoding='utf-8')
            print(f'Updated: {yaml_file.relative_to(config_root)}')

    if plaintext_found:
        for msg in plaintext_found:
            print(msg, file=sys.stderr if dry_run else sys.stdout)
        if dry_run:
            sys.exit(1)
    elif dry_run:
        print('All !encr / !encr_kdf values are already encrypted.')


def _encrypt_fast(key: str, plaintext: str) -> str:
    """AES-GCM v1 (fast path, SHA-256 KDF) — mirrors AESCipher.encrypt without importing pyflexcfg."""
    import hashlib

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    k = hashlib.sha256(key.encode('utf-8')).digest()
    nonce = os.urandom(12)
    ct = AESGCM(k).encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.b64encode(b'\x01' + nonce + ct).decode('ascii')


def _encrypt_kdf(key: str, plaintext: str) -> str:
    """AES-GCM v2 (PBKDF2 KDF) — mirrors AESCipher.encrypt_kdf without importing pyflexcfg."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    passphrase = key.encode('utf-8')
    salt = os.urandom(16)
    k = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000).derive(passphrase)
    nonce = os.urandom(12)
    ct = AESGCM(k).encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.b64encode(b'\x02' + salt + nonce + ct).decode('ascii')


def _is_encrypted(value: str) -> bool:
    try:
        raw = base64.b64decode(value, validate=True)
        return len(raw) >= 14 and raw[0] in (0x01, 0x02)  # noqa: PLR2004
    except Exception:
        return False


if __name__ == '__main__':
    main()
