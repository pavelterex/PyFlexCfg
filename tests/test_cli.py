"""Tests for CLI introspection and encrypt command (Feature 3)."""

import base64
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import TEST_CBC_CIPHERTEXT, TEST_ENCRYPTED_STRING, TEST_KEY, TEST_STRING

from pyflexcfg.components.encryption import AESCipher
from pyflexcfg.components.yaml_loader import YamlLoader

_CLI_CONFIG = Path(__file__).parent / 'test_data' / 'cli_config'
_PYTHON = sys.executable


@pytest.mark.parametrize('args', [('encrypt',), ('encrypt', '--dry-run')], ids=['write', 'dry-run'])
def test_encrypt_config_root_without_yaml_fails(tmp_path, args):
    (tmp_path / 'notes.txt').write_text('secret: !encr myvalue\n', encoding='utf-8')
    result = _run(*args, config_root=tmp_path)

    assert result.returncode == 1, f'a root with no YAML files must fail the run, got stdout {result.stdout!r}'
    assert 'no YAML files' in result.stderr, f'got {result.stderr!r}'
    assert 'already encrypted' not in result.stdout, 'must not report success when nothing was scanned'


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


def test_encrypt_dry_run_flags_fast_ciphertext_under_kdf_tag(tmp_path):
    original = f'secret: !encr_kdf {TEST_ENCRYPTED_STRING}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)

    assert result.returncode == 1, f'a value without the PBKDF2 its tag promises must fail the check: {result.stdout!r}'
    assert 'PBKDF2' in result.stderr, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'dry run must not write'


def test_encrypt_dry_run_reports_legacy_without_writing(tmp_path):
    original = f'secret: !encr {TEST_CBC_CIPHERTEXT}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)

    assert result.returncode == 0, f'legacy ciphertext is not plaintext, got rc {result.returncode}'
    assert 'legacy' in result.stdout.lower(), f'legacy value must be reported, got {result.stdout!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'dry run must not write'


@pytest.mark.parametrize(
    'value',
    [
        pytest.param('|\n  block text', id='block scalar'),
        pytest.param('&anchor anchored', id='anchored scalar'),
        pytest.param('', id='no value'),
    ],
)
def test_encrypt_dry_run_unsupported_scalar_exits_nonzero(tmp_path, value):
    original = f'secret: !encr {value}\nother: 1\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', '--dry-run', config_root=tmp_path)

    assert result.returncode == 1, 'an unsupported value may be plaintext, so the check must fail'
    assert 'encrypt manually' in result.stderr, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'file must stay untouched'


@pytest.mark.parametrize('args', [('encrypt',), ('encrypt', '--dry-run')], ids=['write', 'dry-run'])
def test_encrypt_env_file_key_contradicting_process_refused(tmp_path, args):
    original = 'secret: !encr myvalue\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    (tmp_path / 'secrets.env').write_text('PYFLEX_CFG_KEY=key-from-file\n', encoding='utf-8')
    result = _run(*args, config_root=tmp_path)

    assert result.returncode == 1, f'two different keys must stop the command, got stdout {result.stdout!r}'
    assert 'PYFLEX_CFG_KEY' in result.stderr, f'got {result.stderr!r}'
    assert 'Traceback' not in result.stderr, 'the conflict must be reported as a clean error'
    assert 'key-from-file' not in result.stdout + result.stderr, 'the key must not be printed'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'nothing may be encrypted'


def test_encrypt_fast_ciphertext_under_kdf_tag_wrong_key_left_untouched(tmp_path):
    original = f'secret: !encr_kdf {TEST_ENCRYPTED_STRING}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path, cfg_key='not-the-key')

    assert result.returncode == 1, 'a value that cannot be re-encrypted must fail the run'
    assert 'does not decrypt' in result.stderr, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'file must stay untouched'


def test_encrypt_flow_style_value_encrypted(tmp_path):
    (tmp_path / 'app.yaml').write_text('creds: {user: admin, password: !encr hunter2}\n', encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    creds = yaml.load((tmp_path / 'app.yaml').read_text(encoding='utf-8'), YamlLoader)['creds']

    assert result.returncode == 0, f'got {result.stderr!r}'
    assert creds['user'] == 'admin', 'sibling value in the flow mapping must survive'
    assert creds['password'] == 'hunter2', 'flow-style value must decrypt to the original secret'


def test_encrypt_ignores_tag_text_outside_tag_position(tmp_path):
    original = (
        'note: "docs say write !encr token in yaml"\n'
        'hint: put !encr myvalue here\n'
        'port: 8080  # used to be !encr oldvalue\n'
        '# secret: !encr commented\n'
    )
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    dry_run = _run('encrypt', '--dry-run', config_root=tmp_path)

    assert result.returncode == 0, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'non-tag text must not be rewritten'
    assert dry_run.returncode == 0, 'text that merely mentions !encr is not a plaintext secret'


def test_encrypt_keeps_kdf_ciphertext_under_fast_tag(tmp_path):
    original = f'secret: !encr {AESCipher(TEST_KEY).encrypt_kdf(TEST_STRING)}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    dry_run = _run('encrypt', '--dry-run', config_root=tmp_path)

    assert result.returncode == 0, f'got {result.stderr!r}'
    assert dry_run.returncode == 0, 'a value stronger than its tag requires is not a problem'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'stronger ciphertext must not be downgraded'


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


@pytest.mark.parametrize('kind', ['missing', 'file'])
@pytest.mark.parametrize('args', [('encrypt',), ('encrypt', '--dry-run')], ids=['write', 'dry-run'])
def test_encrypt_missing_config_root_fails(tmp_path, kind, args):
    config_root = tmp_path / 'not_a_dir'
    if kind == 'file':
        config_root.write_text('secret: !encr myvalue\n', encoding='utf-8')
    result = _run(*args, config_root=config_root)

    assert result.returncode == 1, f'a {kind} config root must fail the run, got stdout {result.stdout!r}'
    assert 'is not a directory' in result.stderr, f'got {result.stderr!r}'
    assert 'already encrypted' not in result.stdout, 'must not report success for a root it never scanned'


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


@pytest.mark.parametrize('newline', ['\n', '\r\n'], ids=['LF', 'CRLF'])
def test_encrypt_preserves_line_endings(tmp_path, newline):
    content = newline.join(['name: myapp', 'secret: !encr myvalue', 'port: 8080', ''])
    (tmp_path / 'app.yaml').write_bytes(content.encode('utf-8'))
    _run('encrypt', config_root=tmp_path)
    updated = (tmp_path / 'app.yaml').read_bytes().decode('utf-8')

    assert 'myvalue' not in updated, 'value must be encrypted'
    assert updated.count(newline) == 3, f'line endings changed: {updated!r}'
    assert updated.replace('\r\n', '').count('\n') == (3 if newline == '\n' else 0), f'mixed endings: {updated!r}'


def test_encrypt_preserves_other_keys(tmp_path):
    (tmp_path / 'app.yaml').write_text('name: myapp\nport: 8080\nsecret: !encr myvalue\n', encoding='utf-8')
    _run('encrypt', config_root=tmp_path)
    updated_text = (tmp_path / 'app.yaml').read_text(encoding='utf-8')
    # Check non-encr keys are preserved via raw text (safe_load can't handle !encr tags)
    assert 'name: myapp' in updated_text
    assert 'port: 8080' in updated_text


def test_encrypt_quoted_value_round_trips(tmp_path):
    (tmp_path / 'app.yaml').write_text('secret: !encr "two words"  # keep me\nother: 1\n', encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    updated = (tmp_path / 'app.yaml').read_text(encoding='utf-8')
    loaded = yaml.load(updated, YamlLoader)

    assert result.returncode == 0, f'got {result.stderr!r}'
    assert 'two words' not in updated, 'quoted plaintext must be gone from the file'
    assert loaded['secret'] == 'two words', 'the whole quoted value must be encrypted, not its first word'
    assert '# keep me' in updated, 'trailing comment must survive'
    assert loaded['other'] == 1, 'following key must survive'


@pytest.mark.parametrize('filename', ['.env', 'secrets.env'])
def test_encrypt_reads_key_from_env_file(tmp_path, filename):
    (tmp_path / filename).write_text(f'PYFLEX_CFG_KEY={TEST_KEY}\n', encoding='utf-8')
    (tmp_path / 'app.yaml').write_text('secret: !encr myvalue\n', encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path, cfg_key=None)
    encrypted = (tmp_path / 'app.yaml').read_text(encoding='utf-8').split('!encr ')[1].strip()

    assert result.returncode == 0, f'key from the .env file must be used, got {result.stderr!r}'
    assert AESCipher(TEST_KEY).decrypt(encrypted) == 'myvalue', 'value must be encrypted with the .env key'


def test_encrypt_rewrites_plaintext_value(tmp_path):
    (tmp_path / 'app.yaml').write_text('service:\n  secret: !encr myplainvalue\n', encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    assert result.returncode == 0
    updated = (tmp_path / 'app.yaml').read_text(encoding='utf-8')
    assert 'myplainvalue' not in updated
    assert '!encr ' in updated


@pytest.mark.parametrize('args', [('encrypt',), ('encrypt', '--dry-run')], ids=['write', 'dry-run'])
@pytest.mark.parametrize('second', ['PYFLEX_CFG_KEY=another-key\n', 'UNRELATED=1\n'], ids=['key twice', 'key once'])
def test_encrypt_several_env_files_refused(tmp_path, second, args):
    original = 'secret: !encr myvalue\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    (tmp_path / 'app.env').write_text(f'PYFLEX_CFG_KEY={TEST_KEY}\n', encoding='utf-8')
    (tmp_path / 'backup.env').write_text(second, encoding='utf-8')
    result = _run(*args, config_root=tmp_path, cfg_key=None)

    assert result.returncode == 1, f'more than one .env file must stop the command, got stdout {result.stdout!r}'
    for name in ('app.env', 'backup.env'):
        assert name in result.stderr, f'{name} must be named in the error, got {result.stderr!r}'
    assert 'Traceback' not in result.stderr, 'the refusal must be a clean error'
    assert 'another-key' not in result.stdout + result.stderr, 'no key may be printed'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'nothing may be encrypted'


def test_encrypt_skips_already_encrypted(tmp_path):
    original = f'service:\n  secret: !encr {TEST_ENCRYPTED_STRING}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    _run('encrypt', config_root=tmp_path)
    # File should be unchanged (no rewrite triggered)
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original


@pytest.mark.parametrize('args', [('encrypt',), ('encrypt', '--dry-run')], ids=['write', 'dry-run'])
@pytest.mark.parametrize('raw', [b'PFLX\x01', b'PFLX\x02' + b'\x00' * 20, b'PFLX\x09' + b'\x00' * 60], ids=str)
def test_encrypt_marked_but_invalid_ciphertext_left_untouched(tmp_path, raw, args):
    original = f'secret: !encr {base64.b64encode(raw).decode("ascii")}\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run(*args, config_root=tmp_path)

    assert result.returncode == 1, f'a truncated or unknown-version ciphertext must fail the run: {result.stdout!r}'
    assert 'truncated or of an unknown version' in result.stderr, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'it must not be encrypted as plaintext'


def test_encrypt_unknown_cmd_exits_nonzero():
    result = _run('badcmd')
    assert result.returncode == 1
    assert 'Unknown' in result.stderr or 'Available' in result.stderr


@pytest.mark.parametrize(
    'args',
    [
        pytest.param(('--dryrun',), id='misspelled flag'),
        pytest.param(('--dry_run',), id='underscore flag'),
        pytest.param(('--dry-run', '--verbose'), id='valid flag plus unknown'),
        pytest.param(('some_path',), id='positional argument'),
    ],
)
def test_encrypt_unknown_option_rejected_without_writing(tmp_path, args):
    original = 'secret: !encr myvalue\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', *args, config_root=tmp_path)

    assert result.returncode == 1, f'unknown encrypt arguments must fail, got stdout {result.stdout!r}'
    assert 'Unknown' in result.stderr, f'got {result.stderr!r}'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'file must not be modified'


def test_encrypt_unparsable_file_reported_without_content(tmp_path):
    original = 'secret: !encr myvalue\nbroken: "unclosed hunter2\n'
    (tmp_path / 'app.yaml').write_text(original, encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)

    assert result.returncode == 1, 'a file that cannot be parsed must fail the run'
    assert 'cannot be parsed as YAML' in result.stderr, f'got {result.stderr!r}'
    assert 'hunter2' not in result.stdout + result.stderr, 'file content must not be echoed'
    assert (tmp_path / 'app.yaml').read_text(encoding='utf-8') == original, 'file must stay untouched'


def test_encrypt_upgrades_fast_ciphertext_under_kdf_tag(tmp_path):
    (tmp_path / 'app.yaml').write_text(f'secret: !encr_kdf {TEST_ENCRYPTED_STRING}\n', encoding='utf-8')
    result = _run('encrypt', config_root=tmp_path)
    upgraded = (tmp_path / 'app.yaml').read_text(encoding='utf-8').split('!encr_kdf ')[1].strip()

    assert result.returncode == 0, f'got {result.stderr!r}'
    assert AESCipher.is_kdf(upgraded), 'value under !encr_kdf must end up PBKDF2-encrypted'
    assert AESCipher(TEST_KEY).decrypt(upgraded) == TEST_STRING, 'upgraded value must hold the original secret'


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

    env = {**os.environ, 'PYFLEX_CFG_ROOT_PATH': str(config_root)}
    env.pop('PYFLEX_ENV', None)
    env.pop('PYFLEX_CFG_KEY', None)
    if cfg_key is not None:
        env['PYFLEX_CFG_KEY'] = cfg_key
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [_PYTHON, '-m', 'pyflexcfg', *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
