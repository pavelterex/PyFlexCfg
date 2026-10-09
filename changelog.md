# Changelog

All notable changes to PyFlexCfg are documented here. Newest entries on top.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] — 2026-10-06

### Breaking

- **`!encr` ciphertext format changed (AES-CBC → AES-GCM).** New encryptions use AES-GCM and start
  with the 4-byte marker `PFLX` plus a version byte (base64 prefix `UEZMWA`). Existing CBC
  ciphertexts carry no marker and are **decrypted transparently**, but emit a `logging.WARNING` on
  every load; run `pyflexcfg encrypt` to migrate all values to AES-GCM and silence the warning.
- **Only one `.env` file is allowed in the config root.** 2.x loaded every `*.env` file it found, in
  an order the operating system decided, so a variable defined in two files had an unpredictable
  value. Two or more files now raise `RuntimeError` naming them, on first load, on
  `reload_config()` and in every `pyflexcfg` command. Merge them into one file before upgrading.
- **A file named exactly `.env` is now loaded.** 2.x matched on the file suffix, which is empty for
  the bare `.env` name, so that file was silently ignored. It is now recognised like any other name
  ending in `.env`, and counts towards the one-file limit. A bare `.env` in your config root that
  never took effect will start to.

### Added

- **`!encr_kdf` YAML tag** — AES-GCM encryption with PBKDF2HMAC (SHA-256, 480k iterations, random
  salt) for crown-jewel secrets. `AESCipher.encrypt_kdf(plaintext)` produces the ciphertext.
  `AESCipher.decrypt()` is self-routing: it reads the version byte after the `PFLX` marker (`\x01`
  for fast, `\x02` for KDF) so both tags share the same decrypt path.
- **`AESCipher.is_encrypted()`, `AESCipher.is_kdf()`, `AESCipher.is_legacy()`,
  `AESCipher.has_marker()`, `AESCipher.decrypt_legacy()`** — classify a value as current-format,
  PBKDF2-encrypted, v2-shaped or merely marked, and decrypt a v2 AES-CBC ciphertext explicitly.
  `is_encrypted()` and `is_kdf()` accept only a complete ciphertext; a truncated one is rejected,
  and `decrypt()` reports it as truncated.
- **`PYFLEX_ENV` environment layering.** Set `PYFLEX_ENV=dev` to deep-merge `Cfg.env.dev` into the
  root `Cfg` namespace after YAML loading. Layering order (lowest → highest): base YAML →
  env-layer merge → `CFG__*` env-var overrides → `validate_required()`.
  `Cfg.apply_env_layer()` can be called explicitly; it is also called automatically inside
  `reload_config()`. Layer values are deep-copied into the root, so overrides and runtime changes
  to the effective config never alter the definitions under `Cfg.env`. A tier may be named like a
  dict method (`env/items.yaml`). A layer whose top-level keys are reserved — `env`, private names,
  handler members, non-strings — is rejected with `RuntimeError` before anything is merged.
- **`!required` YAML tag + `Cfg.validate_required()`.** Mark any scalar value `!required` to
  declare it must be supplied at runtime. If any `!required` sentinels survive all override layers,
  `validate_required()` raises `RuntimeError` listing every missing dotted path. Sentinels inside
  lists are detected as well and reported with their index (`app.hosts[1]`). Only the effective
  config is validated: the `env/` layer definitions are skipped, so a `!required` in an inactive
  tier never blocks loading and one in the active tier is reported by its effective path. Only the
  `env/` directory defines layers; a root-level `env.yaml` file is ordinary config and is validated.
- **CLI — `python -m pyflexcfg` (or `pyflexcfg` after install).**
  - `pyflexcfg show` — print the effective merged config as YAML (secrets masked).
  - `pyflexcfg env` — print config root, project root, and active `PYFLEX_ENV`.
  - `pyflexcfg encrypt [--dry-run]` — walk all YAML files, encrypt any plaintext `!encr` /
    `!encr_kdf` values and migrate legacy AES-CBC ciphertexts, in-place. `--dry-run` reports without
    writing and exits 1 if any plaintext is found (drop-in pre-commit hook). Only real YAML tags are
    acted on, so `!encr` mentioned in a string or comment is ignored; plain, quoted and flow-style
    values are handled, and the rest of the file is preserved byte for byte. Values it cannot safely
    rewrite (block scalars, anchored values, tags with no value, unparsable files, legacy-shaped
    values that do not decrypt with the current key) are left untouched, reported on stderr, and
    make the command exit 1. Reports name the file, line, tag and key — never the value. A missing
    or non-directory config root, or one with no YAML files, is an error (exit 1), not an empty scan.
    A fast ciphertext under `!encr_kdf` is re-encrypted with PBKDF2 (and fails `--dry-run`); a
    PBKDF2 ciphertext under `!encr` is left alone.
    A value carrying the marker but truncated or of an unknown version is reported and left alone.
    Any argument other than `--dry-run` is rejected before a file is touched. The config root's
    `*.env` files are loaded first, so `PYFLEX_CFG_KEY` may live there.
- **HashiCorp Vault integration** (`!vault` tag). Install the optional extra `pyflexcfg[vault]`
  (`hvac` dependency). Path format: `mount/path#field` — the `#field` suffix selects a key from
  the secret's data dict; omit it to receive the whole dict as an `AttrDict`. KV v2 is detected
  when `data/` comes directly after the mount (`mount/data/…`); any other path, including one with
  `data` further down, is read as KV v1. The Vault client is created on the
  first `!vault` tag hit and rebuilt whenever `VAULT_ADDR` or `VAULT_TOKEN` changes, so a reload
  after rotating the token uses the new one. A failed fetch raises with the secret path and the
  kind of failure only; the Vault client's message, which can hold the response body, is not
  included or chained. Every non-null leaf fetched — in a single field, a
  whole secret, or a nested object or list — is wrapped in `Secret`; non-string leaves are stored as
  the `Secret` of their text.
- **Warning for config names that dot notation cannot reach.** Python keywords (`class`, `global`),
  non-identifiers (`my-key`), non-string keys (`1`, `true`) and nested keys named like a dict method
  or dunder (`items`, `keys`, `__len__`) still load, but cannot be written as `Cfg.section.name`.
  Each load now logs one WARNING listing them with their paths and the reason, and pointing to item
  access (`Cfg.app['items']`, `getattr(Cfg, 'global')`).
- **Path `::Type` suffixes for `CFG__*` overrides.** `::path`, `::home_dir`, `::proj_root`,
  `::path_posix`, `::path_win`, `::pure_path`, `::pure_path_posix` and `::pure_path_win` turn an
  override into the same path type the YAML tag of that name produces, e.g.
  `CFG__APP__LOG_FILE=/var/log/app.log::path`.
- **Key-length warning**: `AESCipher` emits `logging.WARNING` at instantiation if
  `len(PYFLEX_CFG_KEY) < 32`.
- **`Required` class exported from the package root** (`from pyflexcfg import Required`). Useful
  for programmatic sentinel injection and test assertions.

### Changed

- **`Cfg` loads on first access instead of when the package is imported.** `from pyflexcfg import Cfg`
  behaves as before: it loads the config and raises on a missing config root or unsatisfied
  `!required` key. A bare `import pyflexcfg`, or importing only `AESCipher`, `AttrDict`, `Required`
  or `Secret`, no longer loads anything or needs a config directory; code relying on a bare
  `import pyflexcfg` to fail fast must reference `pyflexcfg.Cfg`. The first load is guarded by a
  lock, so threads requesting `Cfg` simultaneously load it once; `reload_config()` and runtime
  mutation remain unsynchronised.
- **`!string` composes secrets correctly.** A part tagged `!encr`, `!encr_kdf` or `!vault` used to be
  joined as its mask, producing e.g. `'postgresql://app:********@db'`. The real value is now joined
  in and the result is a `Secret`, so `!string ['postgresql://app:', !encr …, '@db']` yields a usable,
  masked connection string. `!string` with no secret part still returns a plain `str`. A `!required`
  part makes the whole composed value required, where it used to become the literal text
  `<required>` and pass validation. The path tags (`!path`, `!home_dir`, `!proj_root` and the pure
  variants) do the same, where a `!required` part used to raise a `TypeError` from `pathlib`.
- **Root-level config names that collide with handler members are rejected on every load path.**
  A file or directory in the config root named `reload_config`, `apply_env_layer`, `update_from_env`,
  `validate_required`, `config_root` or `project_root` now raises `RuntimeError: Namespace conflict`.
  Previously `config_root` and `project_root` were accepted, and all six were accepted when loaded
  through `reload_config()`, replacing the member and breaking later reloads.
- **`CFG__*` overrides resolve their path by key and refuse handler names.** A path through a key
  named like a dict method (`CFG__APP__ITEMS__SIZE=5`) used to be silently ignored and now applies;
  `::yaml_m` onto such a key now merges instead of replacing. An override whose first component is
  private or a handler member (`CFG__RELOAD_CONFIG=…`) used to replace that member on `Cfg` and now
  raises `RuntimeError`.
- **`CFG__*` overrides match keys case-insensitively.** `CFG__APP__APIKEY=…` used to leave a key
  spelled `apiKey` untouched and add a stray `apikey`; it now updates `apiKey`. An exact lowercase
  key still wins, and two keys differing only in case with no exact match raise `RuntimeError`.
  Keys that cannot be spelled in a variable name (`my-key`, names containing `__`, non-strings)
  remain unaddressable; use `::yaml_m` on the parent.
- **`reload_config()` keeps the environment in step with the `.env` file.** When a variable is
  removed from the file, or the file is deleted, the next reload puts the variable back to what the
  process itself provided, or removes it from `os.environ` if the process never set it. A dropped
  `CFG__*` override or Vault credential stops applying, and a process-provided variable the file
  merely repeated is kept. A variable the process changed after PyFlexCfg set it is left alone.
- **`Cfg.reload_config(reset=True)` now drops every config value before loading**, not only
  mapping-valued ones. Top-level scalars and lists set by the env layer, a `CFG__*` override or
  runtime assignment no longer survive a reload after their source is gone. `reset=False` is
  unchanged.

### Security

- **AES-CBC replaced with AES-GCM.** GCM provides authenticated encryption — any ciphertext
  tampering raises `ValueError` at decrypt time rather than silently producing corrupted plaintext.
  The old CBC implementation had no authentication tag.
- **A `.env` file can no longer silently replace process-provided credentials.** For
  `PYFLEX_CFG_KEY`, `VAULT_ADDR` and `VAULT_TOKEN`, a `.env` value that differs from one the process
  provides now raises `RuntimeError` at load (and stops `pyflexcfg encrypt`), instead of winning.
  This closes two cases: a stale file replacing an injected token, and a file redirecting a valid
  token to another Vault address. Identical values, a file supplying a variable the process lacks,
  and rotating a file-provided value on reload all still work. For every other variable the `.env`
  file still overrides the process environment, as in 2.x; that order is now documented.
- **Failed `::Type` conversions no longer expose the value.** `update_from_env()` used to raise
  `Value 'hunter2' could not be cast …` with the original exception chained. The error now names
  the variable and target type only, e.g. `CFG__DB__PASSWORD: value could not be cast as 'int'
  (ValueError)`, and the underlying exception is not chained.
- **Skipped-override debug log no longer prints a config value.** When a `CFG__*` path ran through
  a scalar or list (`CFG__DB__PASSWORD__X=…`), the "cannot assign" debug message included that
  value's `repr`. It now logs only the value's type.
- **Debug log no longer leaks env-var values on unknown `::Type` suffix.** When `update_from_env()`
  encounters an unrecognised type suffix (e.g. `CFG__X=secret::nosuchtype`), the log message now
  records only the type name, never the value that preceded `::` — which could have been a secret.

---

## [2.0.0] — 2026-05-25

### Breaking

- **`AESCipher.encrypt()` returns `str`** (base64 ASCII) instead of `bytes`.
  `decrypt()` still accepts both, so previously stored YAML payloads remain
  valid. Callers doing `isinstance(value, bytes)` on the encrypt result need to
  be updated.
- **`Cfg.update_from_env()` is invoked automatically at import.** Code that
  relied on env overrides taking effect only after an explicit call will see
  them applied earlier.
- **`Cfg.update_from_env()` now type-coerces values** to `int` → `float` →
  `bool` → `str` (in that order) instead of leaving everything as `str` with a
  special case for booleans. Callers expecting string-typed numeric env vars
  must opt out with the new `::str` suffix.
- **`Cfg.reload_config()` signature changed**: `(config_path=None, project_root=None, reset=True)`.
  The old `dct` parameter has been removed (it was only used internally during
  recursion).

### Added

- `Cfg.reload_config(config_path, project_root=None, reset=True)` — re-walk the
  config tree at runtime, optionally pointing at a different directory or
  anchoring `!proj_root` to an explicit path. Enables hot-reload and clean
  test isolation.
- `AttrDict.as_dict()` — recursively unwrap an `AttrDict` (and any nested
  `AttrDict`s inside lists, tuples, sets) back to plain Python containers.
- `Secret.__format__` override — closes a leak where `f'{secret}'` returned
  the underlying string while `repr(secret)` and `str(secret)` were masked.
- `Cfg.__str__` renders the current configuration as formatted YAML via a
  custom dumper that knows about `AttrDict`, `Secret`, and every `Path` flavor.
- `.env` auto-loading: any `*.env` file directly inside the config root is
  loaded via [`python-dotenv`](https://pypi.org/project/python-dotenv/) before
  YAML parsing.
- New YAML constructors:
  - `!path` — host-native `Path`.
  - `!proj_root` — host-native `Path` rooted at the project root.
  - `!pure_path` — OS-default `PurePath`.
  - `!pure_path_posix` — explicit `PurePosixPath`, regardless of host OS.
  - `!pure_path_win` — explicit `PureWindowsPath`, regardless of host OS.
- New env var `PYFLEX_PROJECT_ROOT_PATH` anchoring the `!proj_root`
  constructor. Resolution rule: the env var wins; falling back to `Path.cwd()`
  when `PYFLEX_CFG_ROOT_PATH` is **not** set; and raising `RuntimeError` (only
  when `!proj_root` is actually invoked) when a custom config root is set
  without a project root.
- Explicit `::Type` suffix on env values: `int`, `float`, `bool`, `str`,
  `Secret`, `yaml_m`, `yaml_r`. `::yaml_m` parses the value as YAML and
  **merges** the resulting dict into the existing config dict; `::yaml_r`
  parses as YAML and **replaces** wholesale.
- `Secret` is now re-exported from the package root:
  `from pyflexcfg import Secret`.

### Changed

- Migrated from Poetry to [uv](https://docs.astral.sh/uv/). `pyproject.toml`
  is now PEP 621 compliant; `poetry.lock` replaced by `uv.lock`.
- Build backend switched to Hatchling.
- Docstrings converted from Sphinx `:param:` style to Google `Args:` /
  `Returns:` style per the project style guide.
- README rewritten with a complete table of YAML constructor tags, env-override
  semantics, encryption walkthrough, and uv-based dev commands.

### Fixed

- **Critical:** `Cfg.update_from_env()` no longer uses `exec()`/`eval()` on
  env-var values, closing a code-injection vector. Values are written via
  `setattr` after type coercion through an explicit dispatch dict.
- Namespace conflict detection (directory vs YAML stem) raises `RuntimeError`
  on collision instead of silently overwriting.
- Match-case in `_load_config` no longer double-processes directories whose
  name ends in `.yaml`.
- `HandlerMeta.to_attrdict` no longer mutates tuples in place; type hints
  corrected.
- `AttrDict.__getattr__` re-raises `AttributeError` with `from None` so
  tracebacks stay clean.
- `pytest.ini` typo `-p no:faulthadler` → `-p no:faulthandler`.
- README encryption example no longer shows the `b'…'` byte-repr wrapper.

### Removed

- Dead lazy-conversion branch in `AttrDict.__getattr__` (eager
  `HandlerMeta.to_attrdict` already wraps everything at load time).

## [1.0.0] and earlier

Pre-changelog era. See `git log` for granular history. Notable features in 1.0.0:

- Import-time YAML loading via `HandlerMeta`.
- `!string`, `!path_win`, `!path_posix`, `!home_dir`, `!encr` YAML constructors.
- AES-CBC + PKCS7 encryption (`AESCipher`) using a SHA-256 hashed string key.
- Basic `Cfg.update_from_env()` override mechanism with `::Type` notation
  (later hardened in 2.0.0).
- `NAME_REGEX_STRING` validation for loaded names.
- Centralized `logger` at `pyflexcfg.components.logger`.

[3.0.0]: https://github.com/pavelterex/PyFlexCfg/releases/tag/v3.0.0
[2.0.0]: https://github.com/pavelterex/PyFlexCfg/releases/tag/v2.0.0
[1.0.0]: https://github.com/pavelterex/PyFlexCfg/releases/tag/v1.0.0
