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
| `AESCipher.has_marker(value)` | staticmethod | `True` if the value carries the `PFLX` marker, even truncated or of an unknown version |
| `AESCipher.is_encrypted(value)` | staticmethod | `True` for a complete current-format ciphertext (base64 starts `UEZMWA`) |
| `AESCipher.is_kdf(value)` | staticmethod | `True` for a complete current-format ciphertext made by `encrypt_kdf()` |
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
| `!string [a, b, c]` | sequence | `str` / `Secret` / `Required` | Joins parts: `"abc"`; a `Secret` if any part is one; `Required` if any part is `!required` |
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

Precedence when a setting is given in several places, lowest to highest:

```
YAML files  <  active PYFLEX_ENV layer  <  CFG__* set by the process  <  CFG__* in a .env file
```

The single `.env` file in the config root is loaded first and **overrides the process environment**
for the variables it defines (`CFG__*`, `PYFLEX_ENV`, …); the values are written into `os.environ`.
Any file whose name ends in `.env` counts, the bare `.env` included. On `reload_config()` a variable
no longer in the file (or a deleted file) is put back to what the process itself provided, or
removed from `os.environ` if the process never set it, unless the process changed that variable in
the meantime.

**At most one `.env` file may exist in the config root.** Two or more raise `RuntimeError` naming
them, on first load, on `reload_config()` and in every `pyflexcfg` command; nothing is read into the
environment. Never suggest splitting settings across several `.env` files, and flag stray ones
(`old.env`, `backup.env`) as load-breaking. Version 2 loaded every `.env` file it found.

**Exception to file-wins — `PYFLEX_CFG_KEY`, `VAULT_ADDR`, `VAULT_TOKEN`:** if the process provides
one and the `.env` file gives it a *different* value, loading (and `pyflexcfg encrypt`) raises
`RuntimeError` naming the variable and file, and applies nothing from the file. Same value in both
places is fine, and the variable stays the process's: removing it from the file keeps it, changing
it in the file later is refused. The file may supply one the process lacks; a value that originally
came from the `.env` file may be rotated there and picked up by `reload_config()`.

For other variables PyFlexCfg does not detect conflicts: define each variable in one place.

`PYFLEX_CFG_ROOT_PATH` cannot come from a `.env` file.

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
- **Layers come only from the `env/` directory.** A root-level `env.yaml` file is ordinary config:
  `PYFLEX_ENV` never merges it and its `!required` values are validated normally.
- **`!required` as a part of `!string` or of any path tag makes the whole value required.** The tag
  returns `Required`; it is reported under the composed key and satisfied by overriding that key
  (`CFG__APP__URL=…`, `CFG__APP__LOG_FILE=/var/log/app.log::path`). Without a path suffix an
  override for a path tag yields a plain `str`. In a flow list write `!required ,` or `!required ]` with a space:
  `!required]` is parsed as a tag named `required]` and the file fails to load. A block list avoids
  this.
- **`!required` is validated on the effective config only.** The `env/` layer definitions are
  skipped: a sentinel in `env/prd.yaml` counts only once `PYFLEX_ENV=prd` merges it into the root,
  and is then reported as `database.password`, not `env.prd.database.password`. Sentinels in inactive
  tiers never block loading, and are not caught if code reads `Cfg.env.<tier>` directly.
- **Vault paths are `mount/path#field`; the KV version comes from the path.** `mount/data/…` is read
  as KV v2 (`secret/data/myapp/db` → mount `secret`, path `myapp/db`); any other path is KV v1, even
  with `data` further down (`secret/team/data/app` → path `team/data/app`).
- **The Vault client follows `VAULT_ADDR` / `VAULT_TOKEN`.** It is cached, and rebuilt when either
  value changes, so a reload after rotating the token uses the new one.
- **Vault fetch errors carry the path and the exception class only**, e.g.
  `Failed to fetch Vault secret at 'secret/myapp/db' (Forbidden)`. The hvac message and cause are
  dropped because they can include the raw response body.
- **Env-layer values are deep-copied into the root.** Changing the effective config (override or
  runtime assignment) never changes `Cfg.env.<tier>`.
- **A layer's top-level keys must not be reserved.** `env`, names starting with `_`, handler members
  (`reload_config`, `apply_env_layer`, `update_from_env`, `validate_required`, `config_root`,
  `project_root`) and non-string keys make `apply_env_layer()` raise `RuntimeError` before merging.
  Tier file names are unrestricted beyond the usual name rule (`env/items.yaml` works).
- **`AttrDict` inherits from `dict`.** Use `Cfg.section.key` (attribute) or `Cfg.section['key']`
  (item) — both work. Call `.as_dict()` before passing to code that expects a plain `dict`.
- **Some names load but cannot be read with dot notation**; use item access (`Cfg.app['class']`), or
  `getattr(Cfg, 'global')` for a top-level name. Each load logs one WARNING listing them:
  - Python keywords (`class`, `import`, `global`, `pass`) as keys or as file/directory names.
    Built-ins such as `print`, `list`, `type` are not keywords and work.
  - Keys that are not identifiers (`my-key`, `a.b`, `1st`).
  - Non-string keys: YAML reads `1`, `1.5`, `true`, `off`, `null`, `2024-01-01` as non-strings.
  - Nested keys named like a dict method or dunder (`items`, `keys`, `values`, `get`, `copy`,
    `update`, `__len__`): `Cfg.section.items` is the method. A top-level `config/items.yaml` is fine.
  - Not detectable: `Cfg.app.__token` inside a class body is name-mangled by Python and raises
    `AttributeError`; use `Cfg.app['__token']`.

  Overrides and env layers resolve such keys correctly (`CFG__APP__ITEMS__SIZE=5` works).
- **Root-level files and directories cannot be named after handler members** (`reload_config`,
  `apply_env_layer`, `update_from_env`, `validate_required`, `config_root`, `project_root`); loading
  raises `RuntimeError: Namespace conflict`.
- **PyFlexCfg's log messages are invisible by default.** The `pyflexcfg` logger has only a
  `NullHandler`; warnings (legacy ciphertext, short key, unreachable names) appear only if the
  application configures logging, e.g. `logging.basicConfig()` before importing `Cfg`.
- **`CFG__*` path parts match keys case-insensitively.** An exact lowercase key wins; otherwise the
  one key differing only in case is updated and keeps its spelling (`CFG__APP__APIKEY` → `apiKey`).
  Two case-variants with no exact match (`Host`, `HOST`) raise `RuntimeError`. An unmatched last
  part creates a new lowercase key. Hyphenated keys (`my-key`), keys containing `__` and non-string
  keys cannot be addressed; override the parent with `::yaml_m`, e.g.
  `CFG__APP='{my-key: new}::yaml_m'`.
- **`CFG__*` values take an optional `::Type` suffix.** Scalars: `::int`, `::float`, `::bool`,
  `::str`, `::Secret`; YAML: `::yaml_m` (merge), `::yaml_r` (replace); paths, named after the tag
  giving the same type: `::path`, `::home_dir`, `::proj_root`, `::path_posix`, `::path_win`,
  `::pure_path`, `::pure_path_posix`, `::pure_path_win`. A path suffix takes the whole path as one
  string (`/var/log/app.log::path`). `::proj_root` raises `RuntimeError` when no project root is
  resolvable. Without a suffix the value is auto-coerced `int` → `float` → `bool` → `str`.
- **`CFG__*` overrides cannot target handler names.** A first path component that starts with `_`
  or names a handler member (`reload_config`, `apply_env_layer`, `update_from_env`,
  `validate_required`, `config_root`, `project_root`) raises `RuntimeError`. Paths under `env` are
  allowed.
- **Directory and file names** under the config root must match `^[a-z][a-z0-9_]{0,28}[a-z0-9]$`.
  Files that don't match are silently skipped.
- **`!encr` v2 → v3 migration.** v2 ciphertexts (AES-CBC) still decrypt in v3 but log
  `logging.WARNING` on every load. Migrate with `pyflexcfg encrypt` — it decrypts each legacy value
  with `PYFLEX_CFG_KEY` and rewrites it in-place as AES-GCM. No code changes required; commit the
  updated YAML files.
- **`pyflexcfg encrypt` acts only on real `!encr` / `!encr_kdf` tags** (it tokenizes the YAML), so
  `!encr` mentioned in a string or comment is ignored. Plain, quoted and flow-style values are
  handled. It skips what it cannot safely rewrite — block scalars, anchored values, tags with no
  value, unparsable files, values with the `PFLX` marker that are truncated or of an unknown
  version, and legacy-shaped values that do not decrypt with the current key (wrong
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
