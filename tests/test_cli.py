"""Tests for CLI introspection and encrypt command (Feature 3)."""

import subprocess
import sys
from pathlib import Path

import yaml
from conftest import TEST_CBC_CIPHERTEXT, TEST_ENCRYPTED_STRING, TEST_KEY, TEST_STRING

from pyflexcfg.components.encryption import AESCipher

_CLI_CONFIG = Path(__file__).parent / 'test_data' / 'cli_config'
_PYTHON = sys.executable


def test_encrypt_dry_run_all_clean(tmp_path):
    (tmp_path / 'app.yaml').write_text(f'service:\n  secret: !encr {TEST_ENCRYPTED_STRING}\n', encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)
    assert result.returncode == 0
    assert 'encrypted' in result.stdout.lower()


def test_encrypt_dry_run_finds_plaintext(tmp_path):
    (tmp_path / 'app.yaml').write_text('service:\n  secret: !encr plaintext-value\n', encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)
    assert result.returncode == 1
    assert 'plaintext' in result.stderr.lower() or 'plaintext' in result.stdout.lower()


def test_encrypt_dry_run_reports_legacy_without_writing(tmp_path):
    original = f'secret: !encr {TEST_CBC_CIPHERTEXT}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)

    assert result.returncode == 0, f'legacy ciphertext is not plaintext, got rc {result.returncode}'
    assert 'legacy' in result.stdout.lower(), f'legacy value must be reported, got {result.stdout!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'dry run must not write'


def test_encrypt_dry_run_unsupported_scalar_exits_nonzero(tmp_path):
    original = 'secret: !encr "two words"\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)

    assert result.returncode == 1, 'a quoted value may be plaintext, so the check must fail'
    assert 'unsupported scalar form' in result.stderr, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'file must stay untouched'


def test_encrypt_legacy_wrong_key_left_untouched(tmp_path):
    original = f'secret: !encr {TEST_CBC_CIPHERTEXT}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path, cfg_key='not-the-key')

    assert result.returncode == 1, 'an undecryptable legacy value must fail the run'
    assert 'does not decrypt' in result.stderr, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'value must not be double-encrypted'


def test_encrypt_migrates_legacy_ciphertext(tmp_path):
    (tmp_path / 'app.yaml').write_text(f'secret: !encr {TEST_CBC_CIPHERTEXT}\n', encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    migrated = (tmp_path / 'app.yaml').read_text(encoding='utf-8').split('!encr ')[1].strip()

    assert result.returncode == 0, f'migration failed: {result.stderr!r}'
    assert AESCipher.is_encrypted(migrated), 'migrated value must be in the current format'
    assert AESCipher(TEST_KEY).decrypt(migrated) == TEST_STRING, 'migrated value must hold the original secret'


def test_encrypt_output_omits_values(tmp_path):
    content = f'plain: !encr myplainvalue\nlegacy: !encr {TEST_CBC_CIPHERTEXT}\nquoted: !encr "two words"\n'
    (tmp_path / 'app.yaml').write_text(content, encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)
    output = result.stdout + result.stderr

    for leaked in ('myplainvalue', TEST_STRING, 'two'):
        assert leaked not in output, f'{leaked!r} leaked into CLI output'


def test_encrypt_preserves_comments(tmp_path):
    content = '# top-level comment\nservice:\n  # inline comment\n  secret: !encr myvalue\n'
    (tmp_path / 'app.yaml').write_text(content, encoding='utf-8')
    _run('encrypt', config_root=tmp_path)
    updated = (tmp_path / 'app.yaml').read_text(encoding='utf-8')
    assert '# top-level comment' in updated
    assert '# inline comment' in updated


def test_encrypt_preserves_other_keys(tmp_path):
    (tmp_path / 'app.yaml').write_text('name: myapp\nport: 8080\nsecret: !encr myvalue\n', encoding='utf-8')
    _run('encrypt', config_root=tmp_path)
    updated_text = (tmp_path / 'app.yaml').read_text(encoding='utf-8')
    # Check non-encr keys are preserved via raw text (safe_load can't handle !encr tags)
    assert 'name: myapp' in updated_text
    assert 'port: 8080' in updated_text


def test_encrypt_rewrites_plaintext_value(tmp_path):
    (tmp_path / 'app.yaml').write_text('service:\n  secret: !encr myplainvalue\n', encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    assert result.returncode == 0
    updated = (tmp_path / 'app.yaml').read_text(encoding='utf-8')
    assert 'myplainvalue' not in updated
    assert '!encr ' in updated


def test_encrypt_skips_already_encrypted(tmp_path):
    original = f'service:\n  secret: !encr {TEST_ENCRYPTED_STRING}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    _run('encrypt', config_root=tmp_path)
    # File should be unchanged (no rewrite triggered)
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original


def test_encrypt_unknown_cmd_exits_nonzero():
    result = _run('badcmd')
    assert result.returncode == 1
    assert 'Unknown' in result.stderr or 'Available' in result.stderr


def test_env_not_set_shows_placeholder():
    result = _run('env')
    assert result.returncode == 0
    assert '(not set)' in result.stdout


def test_env_prints_active_env():
    result = _run('env', extra_env={'PYFLEX_ENV': 'staging'})
    assert result.returncode == 0
    assert 'staging' in result.stdout


def test_env_prints_config_root():
    result = _run('env')
    assert result.returncode == 0
    assert str(_CLI_CONFIG) in result.stdout


def test_show_masks_secrets():
    result = _run('show')
    assert result.returncode == 0
    assert '********' in result.stdout


def test_show_prints_config_yaml():
    result = _run('show')
    assert result.returncode == 0
    assert result.stdout.strip()
    parsed = yaml.safe_load(result.stdout)
    assert isinstance(parsed, dict)
    assert 'app' in parsed


def _run(*args, config_root=_CLI_CONFIG, extra_env=None, cfg_key=TEST_KEY):
    """Run `python -m pyflexcfg <args>` with a controlled environment."""
    import os

    env = {**os.environ, 'PYFLEX_CFG_ROOT_PATH': str(config_root), 'PYFLEX_CFG_KEY': cfg_key}
    env.pop('PYFLEX_ENV', None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [_PYTHON, '-m', 'pyflexcfg', *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
