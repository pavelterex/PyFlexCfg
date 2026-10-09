# AGENTS.md — PyFlexCfg reference for AI coding assistants

PyFlexCfg is a YAML configuration loader for Python that needs no init call. It walks a directory
of YAML files the first time `Cfg` is imported and exposes the combined tree as attribute-access
namespaces on that single global class `Cfg` (not an instance). It supports encrypted secrets,
environment-variable overrides, env-specific config layering, required-key validation, a CLI, and
optional HashiCorp Vault integration.

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
| `AESCipher.encrypt(plaintext)` | method | AES-GCM v1 (SHA-256 KDF) → base64 str, header `PFLX\x01` |
| `AESCipher.encrypt_kdf(plaintext)` | method | AES-GCM v2 (PBKDF2, 480k iters) → base64 str, header `PFLX\x02` |
| `AESCipher.decrypt(ciphertext)` | method | Routes by `PFLX` marker + version byte; no marker → v2 AES-CBC |
| `AESCipher.decrypt_legacy(ciphertext)` | method | Decrypt a v2 AES-CBC ciphertext; no migration warning |
| `AESCipher.is_encrypted(value)` | staticmethod | `True` for a current-format ciphertext (base64 starts `UEZMWA`) |
| `AESCipher.is_kdf(value)` | staticmethod | `True` for a current-format ciphertext made by `encrypt_kdf()` |
| `AESCipher.is_legacy(value)` | staticmethod | `True` for a value shaped like a v2 AES-CBC ciphertext |
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
| `!required` | scalar | `Required` | Raises when `Cfg` loads if not satisfied by an override |
| `!vault <path>#<field>` | scalar | `Secret` | Fetches from HashiCorp Vault; needs `hvac` installed |
| `!vault <path>` | scalar | `AttrDict` | Whole secret; every leaf is a `Secret` |
| `!string [a, b, c]` | sequence | `str` / `Secret` | Joins parts: `"abc"`; a `Secret` if any part is one |
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
- **Config loading fires the first time `Cfg` is requested from the package** — normally the
  `from pyflexcfg import Cfg` line — inside the metaclass `__new__`. There is no explicit `init()`.
  Without a valid config root that line raises `RuntimeError`. A bare `import pyflexcfg`, or
  importing only `AESCipher` / `AttrDict` / `Required` / `Secret`, loads nothing and cannot fail
  this way.
- **Only the first load is thread-safe.** Concurrent first requests for `Cfg` load it once behind a
  lock. `Cfg.reload_config()` and runtime mutation of `Cfg` are not synchronised.
- **In tests**, call `Cfg.reload_config(config_path=...)` to switch config roots between cases.
  The `restore_cfg_after_test` autouse fixture in `conftest.py` does this automatically.
- **`!encr` decrypts at YAML parse time**, not at attribute access. `PYFLEX_CFG_KEY` must be set
  before `Cfg` is first imported, not just before accessing the encrypted value.
- **`!required` raises when `Cfg` loads** (the load ends with `validate_required()`), not when the
  missing key is accessed. Sentinels inside lists are found too and reported with an index
  (`app.hosts[1]`, `app.servers[0].host`); satisfy them by replacing the whole list, e.g.
  `CFG__APP__HOSTS='[a, b]::yaml_r'`.
- **`!required` is validated on the effective config only.** The `Cfg.env` layer definitions are
  skipped: a sentinel in `env/prd.yaml` counts only once `PYFLEX_ENV=prd` merges it into the root,
  and is then reported as `database.password`, not `env.prd.database.password`. Sentinels in inactive
  tiers never block loading, and are not caught if code reads `Cfg.env.<tier>` directly.
- **The Vault client follows `VAULT_ADDR` / `VAULT_TOKEN`.** It is cached, and rebuilt when either
  value changes, so a reload after rotating the token uses the new one.
- **`AttrDict` inherits from `dict`.** Use `Cfg.section.key` (attribute) or `Cfg.section['key']`
  (item) — both work. Call `.as_dict()` before passing to code that expects a plain `dict`.
- **Directory and file names** under the config root must match `^[a-z][a-z0-9_]{0,28}[a-z0-9]$`.
  Files that don't match are silently skipped.
- **`!encr` v2 → v3 migration.** v2 ciphertexts (AES-CBC) still decrypt in v3 but log
  `logging.WARNING` on every load. Migrate with `pyflexcfg encrypt` — it decrypts each legacy value
  with `PYFLEX_CFG_KEY` and rewrites it in-place as AES-GCM. No code changes required; commit the
  updated YAML files.
- **`pyflexcfg encrypt` acts only on real `!encr` / `!encr_kdf` tags** (it tokenizes the YAML), so
  `!encr` mentioned in a string or comment is ignored. Plain, quoted and flow-style values are
  handled. It skips what it cannot safely rewrite — block scalars, anchored values, tags with no
  value, unparsable files, and legacy-shaped values that do not decrypt with the current key (wrong
  key, or plaintext that is itself base64 of 32/48/64… bytes). These are reported on stderr and the
  command exits 1; encrypt them manually with `AESCipher.encrypt()`.
- **The tag does not enforce the ciphertext kind at load time.** `!encr` and `!encr_kdf` both decrypt
  either kind. Put an `encrypt_kdf()` ciphertext under `!encr_kdf`; `pyflexcfg encrypt` upgrades a
  fast ciphertext found there and `--dry-run` exits 1 on it. A KDF ciphertext under `!encr` is left
  alone.
- **`Cfg.reload_config()` with the default `reset=True` drops every config value first**, including
  ones set by the env layer, `CFG__*` overrides or runtime assignment. `reset=False` keeps anything
  the new load does not overwrite.
- **Every `!vault` leaf is a `Secret` holding text.** A Vault number or boolean arrives as
  `Secret('5432')` / `Secret('True')`; convert with `int(...)` or compare to `'True'` — `bool()` on it
  is always truthy. `null` stays `None`.
- **Compose secret-bearing strings with `!string`, never with formatting.** In YAML,
  `url: !string ['postgresql://app:', !encr <ciphertext>, '@db:5432/main']` yields a `Secret` holding
  the full real value (`!vault` parts work too). In code, `f'{secret}'`, `'{}'.format(secret)` and
  `'%s' % secret` all insert `********`; use `'prefix' + secret + 'suffix'` or `''.join([...])`, and
  wrap the result in `Secret(...)` to keep it masked. Path tags (`!path` etc.) cannot mask a secret.
- **Ciphertext format is `PFLX` + version byte + payload.** Never detect encryption by the first
  byte alone; use `AESCipher.is_encrypted()`.

---

## Test environment setup

```python
# Must happen BEFORE Cfg is first imported
import os
os.environ['PYFLEX_CFG_ROOT_PATH'] = '/path/to/config'
os.environ['PYFLEX_CFG_KEY'] = 'test-key-at-least-32-chars-long!!'

from pyflexcfg import Cfg  # config loads here
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
