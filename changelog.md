# Changelog

All notable changes to PyFlexCfg are documented here. Newest entries on top.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] — 2026-05-25

### Breaking

- **`AESCipher.encrypt()` returns `str`** (base64 ASCII) instead of `bytes`.
  `decrypt()` still accepts both, so previously stored YAML payloads remain
  valid. Callers doing `isinstance(value, bytes)` on the encrypt result need to
  be updated.
- **`Cfg.update_from_env()` is invoked automatically at import time.** Code that
  relied on env overrides taking effect only after an explicit call will see
  them applied earlier.
- **`Cfg.update_from_env()` now type-coerces values** to `int` → `float` →
  `bool` → `str` (in that order) instead of leaving everything as `str` with a
  special case for booleans. Callers expecting string-typed numeric env vars
  must opt out with the new `::str` suffix.

### Added

- `Cfg.reload_config(path=None, reset=True)` — re-walk the config tree at
  runtime, optionally pointing at a different directory. Enables hot-reload and
  clean test isolation.
- `AttrDict.as_dict()` — recursively unwrap an `AttrDict` (and any nested
  `AttrDict`s inside lists, tuples, sets) back to plain Python containers.
- `Secret.__format__` override — closes a leak where `f'{secret}'` returned the
  underlying string while `repr(secret)` and `str(secret)` were masked.
- `Cfg.__str__` renders the current configuration as formatted YAML via a
  custom dumper that knows about `AttrDict`, `Secret`, and every `Path` flavor.
- `.env` auto-loading: any `*.env` file directly inside the config root is
  loaded via [`python-dotenv`](https://pypi.org/project/python-dotenv/) before
  YAML parsing.
- New YAML constructors:
  - `!path` — host-native `Path`.
  - `!proj_root` — host-native `Path` rooted at the project root (see below).
  - `!pure_path` — OS-default `PurePath`.
  - `!pure_path_posix` — explicit `PurePosixPath`, regardless of host OS.
  - `!pure_path_win` — explicit `PureWindowsPath`, regardless of host OS.
- New env var `PYFLEX_PROJECT_ROOT_PATH` anchoring the `!proj_root` constructor. Resolution rule:
  the env var wins; falling back to `Path.cwd()` when `PYFLEX_CFG_ROOT_PATH` is **not** set; and
  raising `RuntimeError` (only when `!proj_root` is actually invoked) when a custom config root
  is set without a project root.
- `Cfg.reload_config(path, project_root=None, reset=True)` gained a `project_root` keyword for
  programmatic override without touching the environment.
- Explicit `::Type` suffix on env values: `int`, `float`, `bool`, `str`,
  `Secret`, `yaml_m`, `yaml_r`. `::yaml_m` parses the value as YAML and
  **merges** the resulting dict into the existing config dict (no-op for
  non-dict values); `::yaml_r` parses as YAML and **replaces** wholesale.
- Match-case dispatch in `_load_config`; unsupported items are logged at DEBUG
  level instead of silently skipped.
- `Secret` is now re-exported from the package root:
  `from pyflexcfg import Secret`.

### Changed

- Migrated from Poetry to [uv](https://docs.astral.sh/uv/). `pyproject.toml` is
  now PEP 621 compliant; `poetry.lock` replaced by `uv.lock`.
- Build backend switched to Hatchling.
- Project minimum Python version reaffirmed at 3.10.
- Docstrings converted from Sphinx `:param:` style to Google `Args:` /
  `Returns:` style per the project style guide.
- README rewritten with a complete table of YAML constructor tags, env-override
  semantics, encryption walkthrough, and uv-based dev commands.

### Fixed

- **Critical:** `Cfg.update_from_env()` no longer uses `exec()` on env-var
  values, closing a code-injection vector. Values are written via `setattr`
  after type coercion.
- Namespace conflict detection (directory vs YAML stem) now actually triggers —
  the previous `try/except KeyError` guard never fired because
  `dict.__setitem__` does not raise `KeyError`.
- Directories whose name happens to end in `.yaml` are no longer processed
  twice (`if`/`if` → `match` covers both branches exclusively).
- `HandlerMeta.to_attrdict` no longer claims `AnyStr | AttrDict | Sequence`
  (meaningless for `AnyStr` outside a generic signature) and no longer mutates
  tuples in place.
- `AttrDict.__getattr__` re-raises `AttributeError` with `from None` so
  tracebacks stay clean.
- `pytest.ini` typo `-p no:faulthadler` → `-p no:faulthandler` (the misspelled
  name was silently ignored, so the option had never done anything).
- README encryption example no longer shows the `b'…'` byte-repr wrapper, which
  would have failed base64 decoding.
- Various README typos.

### Removed

- Dead lazy-conversion branch in `AttrDict.__getattr__` (eager
  `HandlerMeta.to_attrdict` already wraps everything at load time).

## [1.0.0] and earlier

Pre-changelog era. See `git log` for granular history. Notable features in 1.0.0:

- Import-time YAML loading via `HandlerMeta`.
- `!string`, `!path_win`, `!path_posix`, `!home_dir`, `!encr` YAML constructors.
- AES-CBC + PKCS7 encryption (`AESCipher`) using a SHA-256 hashed string key.
- Basic `Cfg.update_from_env()` override mechanism.

[2.0.0]: https://github.com/pavelterex/PyFlexCfg/releases/tag/v2.0.0
[1.0.0]: https://github.com/pavelterex/PyFlexCfg/releases/tag/v1.0.0
