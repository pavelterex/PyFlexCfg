# AGENTS.md — PyFlexCfg reference for AI coding assistants

PyFlexCfg is an import-time YAML configuration loader for Python. It walks a directory of YAML
files and exposes the combined tree as attribute-access namespaces on a single global class `Cfg`
(not an instance). It supports encrypted secrets, environment-variable overrides, env-specific
config layering, required-key validation, a CLI, and optional HashiCorp Vault integration.

---

## Public API

| Symbol | Kind | Description |
|---|---|---|
| `Cfg` | class (`ConfigHandler`) | Global config object — access as `Cfg.section.key` |
| `Cfg.reload_config(config_path, project_root, reset)` | classmethod | Re-walk the config tree |
| `Cfg.update_from_env()` | classmethod | Apply `CFG__*` env-var overrides |
| `Cfg.apply_env_layer()` | classmethod | Merge `Cfg.env.{PYFLEX_ENV}` into root namespace |
| `Cfg.validate_required()` | classmethod | Raise `RuntimeError` if any `!required` key is unset |
| `AESCipher(key)` | class | Encrypt/decrypt secrets for `!encr` / `!encr_kdf` |
| `AESCipher.encrypt(plaintext)` | method | AES-GCM v1 (SHA-256 KDF) → base64 str |
| `AESCipher.encrypt_kdf(plaintext)` | method | AES-GCM v2 (PBKDF2, 480k iters) → base64 str |
| `AESCipher.decrypt(ciphertext)` | method | Self-routing by version byte `\x01`/`\x02` |
| `AttrDict` | class | `dict` subclass exposing keys as attributes |
| `Required` | class | Sentinel for `!required` tag; importable for programmatic injection/testing |
| `Secret` | class | `str` subclass that masks itself in all repr/str/format output |

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `PYFLEX_CFG_ROOT_PATH` | yes (or `./config` must exist) | Absolute path to config root directory |
| `PYFLEX_CFG_KEY` | only with `!encr` / `!encr_kdf` | AES passphrase (≥ 32 chars recommended) |
| `PYFLEX_PROJECT_ROOT_PATH` | only with `!proj_root` | Absolute project root for `!proj_root` resolution |
| `PYFLEX_ENV` | no | Active env name; triggers `apply_env_layer()` deep-merge |
| `CFG__SEC__KEY` | no | Override `Cfg.sec.key`; `__` is the path separator |
| `VAULT_ADDR` | only with `!vault` | HashiCorp Vault server URL |
| `VAULT_TOKEN` | only with `!vault` | Vault auth token |

---

## YAML tags

| Tag | Input | Returns | Notes |
|---|---|---|---|
| `!encr <base64>` | scalar | `Secret` | Decrypts with `PYFLEX_CFG_KEY` (AES-GCM v1) |
| `!encr_kdf <base64>` | scalar | `Secret` | Same + PBKDF2 KDF; slower, for critical secrets |
| `!required` | scalar | `Required` | Raises at startup if not satisfied by an override |
| `!vault <path>#<field>` | scalar | `Secret` | Fetches from HashiCorp Vault; needs `hvac` installed |
| `!string [a, b, c]` | sequence | `str` | Joins parts: `"abc"` |
| `!path [a, b]` | sequence | `Path` | `Path(a, b)` (host-native) |
| `!path_win [a, b]` | sequence | `PureWindowsPath` | |
| `!path_posix [a, b]` | sequence | `PurePosixPath` | |
| `!proj_root [sub, dir]` | sequence | `Path` | Rooted at `PYFLEX_PROJECT_ROOT_PATH` |
| `!home_dir [sub]` | sequence | `Path` | Rooted at `Path.home()` |

---

## Load-time priority order

```
Base YAML  →  env-layer merge (PYFLEX_ENV)  →  CFG__ env-var overrides  →  validate_required()
```

---

## Critical gotchas

- **`Cfg` is a class, not an instance.** Always `Cfg.key`, never `cfg = Cfg(); cfg.key`.
- **Config loading fires at import time** inside the metaclass `__new__`. There is no lazy loading
  and no explicit `init()`. Importing `pyflexcfg` without a valid config root raises `RuntimeError`
  immediately.
- **In tests**, call `Cfg.reload_config(config_path=...)` to switch config roots between cases.
  The `_restore_cfg_after_test` autouse fixture in `conftest.py` does this automatically.
- **`!encr` decrypts at YAML parse time**, not at attribute access. `PYFLEX_CFG_KEY` must be set
  before any `import pyflexcfg`, not just before accessing the encrypted value.
- **`!required` raises at startup** (end of `__init__.py` call to `validate_required()`), not at
  attribute access time.
- **`AttrDict` inherits from `dict`.** Use `Cfg.section.key` (attribute) or `Cfg.section['key']`
  (item) — both work. Call `.as_dict()` before passing to code that expects a plain `dict`.
- **Directory and file names** under the config root must match `^[a-z][a-z0-9_]{0,28}[a-z0-9]$`.
  Files that don't match are silently skipped.
- **`!encr` v2 → v3 migration.** v2 ciphertexts (AES-CBC) still decrypt in v3 but log
  `logging.WARNING` on every load. Migrate with `pyflexcfg encrypt` — rewrites all legacy
  ciphertexts in-place to AES-GCM. No code changes required; commit the updated YAML files.

---

## Test environment setup

```python
# Must happen BEFORE any pyflexcfg import
import os
os.environ['PYFLEX_CFG_ROOT_PATH'] = '/path/to/config'
os.environ['PYFLEX_CFG_KEY'] = 'test-key-at-least-32-chars-long!!'

from pyflexcfg import Cfg  # metaclass fires here
```

---

## Minimal working example

```yaml
# config/app.yaml
name: my-app
debug: false
db:
  host: !required
  port: 5432
  password: !encr <generate with AESCipher.encrypt()>
```

```python
import os
os.environ['PYFLEX_CFG_ROOT_PATH'] = 'config'
os.environ['PYFLEX_CFG_KEY'] = 'my-secret-key-32chars-or-longer!'
os.environ['CFG__APP__DB__HOST'] = 'localhost'

from pyflexcfg import Cfg

print(Cfg.app.name)         # 'my-app'
print(Cfg.app.db.host)      # 'localhost'   (from CFG__ override)
print(Cfg.app.db.password)  # '********'   (Secret instance)
```
