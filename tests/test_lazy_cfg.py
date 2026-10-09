"""`Cfg` loads on first access; importing the package alone needs no config root."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import TEST_KEY

import pyflexcfg
from pyflexcfg.config_handler import ConfigHandler

_CLI_CONFIG = Path(__file__).parent / 'test_data' / 'cli_config'
_REQUIRED_CONFIG = Path(__file__).parent / 'test_data' / 'required_config'
_RETRY_CODE = """
import os
import pyflexcfg

os.environ['CFG__ADHOC'] = 'temporary'
try:
    pyflexcfg.Cfg
except RuntimeError:
    print('first access failed')

del os.environ['CFG__ADHOC']
os.environ['CFG__APP__SERVER__HOST'] = 'srv'
os.environ['CFG__APP__DATABASE__HOST'] = 'db'
os.environ['CFG__APP__DATABASE__PASSWORD'] = 'pw'
cfg = pyflexcfg.Cfg
print('leftover:', hasattr(cfg, 'adhoc'))
print('host:', cfg.app.server.host)
"""


def test_cfg_access_without_config_root_raises(tmp_path):
    result = _run_code('import pyflexcfg; print("imported"); pyflexcfg.Cfg', cwd=tmp_path)

    assert 'imported' in result.stdout, f'bare package import must succeed, got {result.stderr!r}'
    assert result.returncode != 0, 'accessing Cfg without a config root must fail'
    assert 'RuntimeError' in result.stderr, f'got {result.stderr!r}'


@pytest.mark.parametrize('arg', ['encrypt', 'serve'])
def test_cfg_importable_whatever_the_process_arguments(tmp_path, arg):
    result = _run_code('from pyflexcfg import Cfg; print(Cfg.app.service.name)', arg, cwd=tmp_path, root=_CLI_CONFIG)

    assert result.returncode == 0, f'Cfg import failed with argv[1]={arg!r}: {result.stderr!r}'
    assert result.stdout.strip(), 'a config value must be printed'


def test_cfg_loads_once_under_concurrent_first_access(monkeypatch):
    thread_count = 8
    barrier = threading.Barrier(thread_count)
    apply_calls = []
    results = []
    original_apply = ConfigHandler.apply_env_layer

    def slow_apply() -> None:
        apply_calls.append(1)
        time.sleep(0.05)
        original_apply()

    def request_cfg() -> None:
        barrier.wait()
        results.append(pyflexcfg.Cfg)

    monkeypatch.setattr(ConfigHandler, 'apply_env_layer', staticmethod(slow_apply))
    monkeypatch.delitem(pyflexcfg.__dict__, 'Cfg')

    threads = [threading.Thread(target=request_cfg) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(apply_calls) == 1, f'post-load steps ran {len(apply_calls)} times, expected once'
    assert results == [ConfigHandler] * thread_count, 'every thread must receive the loaded Cfg'


def test_cfg_retry_after_failed_first_access_starts_clean(tmp_path):
    result = _run_code(_RETRY_CODE, cwd=tmp_path, root=_REQUIRED_CONFIG)
    lines = result.stdout.splitlines()

    assert result.returncode == 0, f'the retry must succeed once the required keys are supplied: {result.stderr!r}'
    assert 'first access failed' in lines, f'the first access must fail on the required keys, got {lines!r}'
    assert 'leftover: False' in lines, f'a failed first access left its override on the config: {lines!r}'
    assert 'host: srv' in lines, f'the retry must apply the current overrides, got {lines!r}'


def test_first_load_rejects_more_than_one_env_file(tmp_path):
    (tmp_path / 'app.yaml').write_text('key: value\n', encoding='utf-8')
    (tmp_path / 'app.env').write_text('ENV_PROBE_A=1\n', encoding='utf-8')
    (tmp_path / 'backup.env').write_text('ENV_PROBE_B=1\n', encoding='utf-8')
    result = _run_code('from pyflexcfg import Cfg', cwd=tmp_path, root=tmp_path)

    assert result.returncode != 0, 'a config root with two .env files must not load'
    assert 'app.env' in result.stderr, f'the error must name both files, got {result.stderr!r}'
    assert 'backup.env' in result.stderr, f'the error must name both files, got {result.stderr!r}'


@pytest.mark.parametrize('stem', ['config_root', 'project_root', 'reload_config'])
def test_first_load_rejects_root_name_colliding_with_handler_member(tmp_path, stem):
    (tmp_path / f'{stem}.yaml').write_text('key: value\n', encoding='utf-8')
    result = _run_code('from pyflexcfg import Cfg', cwd=tmp_path, root=tmp_path)

    assert result.returncode != 0, f'a root file named {stem}.yaml must not load'
    assert 'Namespace conflict' in result.stderr, f'got {result.stderr!r}'


def test_package_imports_without_config_root(tmp_path):
    code = 'from pyflexcfg import AESCipher, AttrDict, Required, Secret; print("ok")'
    result = _run_code(code, cwd=tmp_path)

    assert result.returncode == 0, f'non-Cfg exports must not need a config root: {result.stderr!r}'


def test_required_validated_on_first_cfg_access(tmp_path):
    result = _run_code('import pyflexcfg; print("imported"); pyflexcfg.Cfg', cwd=tmp_path, root=_REQUIRED_CONFIG)

    assert 'imported' in result.stdout, f'bare package import must succeed, got {result.stderr!r}'
    assert 'Required config values are missing' in result.stderr, f'got {result.stderr!r}'


def test_star_import_exposes_cfg(tmp_path):
    result = _run_code('from pyflexcfg import *; print(Cfg.app.service.name)', cwd=tmp_path, root=_CLI_CONFIG)

    assert result.returncode == 0, f'star import must expose Cfg: {result.stderr!r}'


def test_unknown_attribute_raises():
    with pytest.raises(AttributeError, match='no_such_name'):
        pyflexcfg.no_such_name  # noqa: B018


def _run_code(code: str, *args: str, cwd: Path, root: Path | None = None) -> subprocess.CompletedProcess:
    """Run `python -c code *args` from `cwd`, with the config root set only when given."""
    env = {**os.environ, 'PYFLEX_CFG_KEY': TEST_KEY}
    env.pop('PYFLEX_CFG_ROOT_PATH', None)
    env.pop('PYFLEX_ENV', None)
    if root:
        env['PYFLEX_CFG_ROOT_PATH'] = str(root)

    return subprocess.run(
        [sys.executable, '-c', code, *args], capture_output=True, text=True, env=env, cwd=cwd, check=False
    )
