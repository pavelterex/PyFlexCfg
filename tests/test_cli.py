"""Tests for CLI introspection and encrypt command (Feature 3)."""

import subprocess
import sys
from pathlib import Path

import yaml

_CLI_CONFIG = Path(__file__).parent / 'test_data' / 'cli_config'
_PYTHON = sys.executable


def test_encrypt_dry_run_all_clean(tmp_path):
    encrypted = 'AaYCtE54eHB71gVjFhUTSt+tsNjurjJszBsaNLeEOv+SWpdTjfJ6YC33B5ODWPs='
    (tmp_path / 'app.yaml').write_text(f'service:\n  secret: !encr {encrypted}\n', encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)
    assert result.returncode == 0
    assert 'encrypted' in result.stdout.lower()


def test_encrypt_dry_run_finds_plaintext(tmp_path):
    (tmp_path / 'app.yaml').write_text('service:\n  secret: !encr plaintext-value\n', encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)
    assert result.returncode == 1
    assert 'plaintext' in result.stderr.lower() or 'plaintext' in result.stdout.lower()


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
    encrypted = 'AaYCtE54eHB71gVjFhUTSt+tsNjurjJszBsaNLeEOv+SWpdTjfJ6YC33B5ODWPs='
    original = f'service:\n  secret: !encr {encrypted}\n'
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


def _run(*args, config_root=_CLI_CONFIG, extra_env=None, cfg_key='1234'):
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
