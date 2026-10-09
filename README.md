# PyFlexCfg

**Flexible, zero-boilerplate YAML configuration for Python.** Drop a directory of YAML files next to
your code, import `Cfg`, and every key is instantly reachable as an attribute — no schema, no init
call, no glue code.

```python
from pyflexcfg import Cfg

print(Cfg.database.host)      # loaded from config/database.yaml
print(Cfg.app.api_key)        # '********'  — a Secret, masked everywhere
```

## Why PyFlexCfg?

| Need | How PyFlexCfg covers it |
|---|---|
| Clean attribute access | `Cfg.section.key` — no brackets, no string keys |
| Per-environment config | `PYFLEX_ENV=staging` deep-merges `config/env/staging.yaml` into root |
| Secrets that never leak | `!encr` / `!encr_kdf` tags; `Secret` masks itself in all repr/str/log output |
| Mandatory keys | `!required` tag raises at startup listing every missing dotted path |
| Env-var overrides | `CFG__DB__PORT=5433` overrides `Cfg.db.port` — no extra code |
| HashiCorp Vault | `!vault secret/data/myapp#key` fetches at load time |
| Introspection | `pyflexcfg show` prints the effective config as YAML (secrets masked) |

## Contents

1. [Installation](#installation)
2. [Quick start](#quick-start)
3. [Configuration root and project root](#configuration-root-and-project-root)
4. [`.env` files](#env-files)
5. [Environment-variable overrides](#environment-variable-overrides)
6. [Environment layering (`PYFLEX_ENV`)](#environment-layering-pyflex_env)
7. [Required keys (`!required`)](#required-keys-required)
8. [Custom YAML constructors](#custom-yaml-constructors)
9. [Handling secrets](#handling-secrets)
10. [HashiCorp Vault](#hashicorp-vault)
11. [CLI](#cli)
12. [Runtime reload](#runtime-reload)
13. [Logging](#logging)
14. [Development](#development)

---

## Installation

```shell
pip install pyflexcfg
```

For HashiCorp Vault support:

```shell
pip install "pyflexcfg[vault]"
```

---

## Quick start

Given this layout:

```text
project/
├── config/
│   ├── database.yaml      # host: localhost  port: 5432
│   ├── app.yaml           # name: my-app  debug: false
│   └── env/
│       ├── dev.yaml       # database:\n  host: dev-db
│       └── prd.yaml       # database:\n  host: prd-db  port: 5433
└── app.py
```

```python
# app.py
from pyflexcfg import Cfg

print(Cfg.database.host)   # 'localhost'
print(Cfg.app.name)        # 'my-app'
print(Cfg.env.dev.database.host)  # 'dev-db'
```

Activate an environment tier so its values merge into the root namespace:

```shell
PYFLEX_ENV=dev python app.py
# Cfg.database.host == 'dev-db'
# Cfg.database.port == 5432  (unchanged — deep merge, not replace)
```

Directory and file names must be lowercase identifiers matching `^[a-z][a-z0-9_]{0,28}[a-z0-9]$`.
Names that don't match are silently skipped during loading.

A file or directory directly in the config root may not be named after a member of `Cfg` itself:
`reload_config`, `apply_env_layer`, `update_from_env`, `validate_required`, `config_root` or
`project_root`. Loading such a tree raises `RuntimeError: Namespace conflict`.

### Names that dot notation cannot reach

Keys inside a YAML file are not restricted, and neither are Python keywords as file names. Some of
those names load fine but cannot be written as `Cfg.section.name`:

| Kind of name | Examples | Why dot notation fails |
|---|---|---|
| Python keyword | `class`, `import`, `global`, `pass`, `from` | `Cfg.app.class` is a syntax error |
| Not an identifier | `my-key`, `with space`, `a.b`, `1st` | It cannot be written as an attribute |
| Not a string | `1`, `1.5`, `true`, `off`, `null`, `2024-01-01` | YAML reads these keys as numbers, booleans, null or dates |
| A dict method or dunder | `items`, `keys`, `values`, `get`, `copy`, `update`, `__len__` | `Cfg.app.items` is the dict's own method |

Built-in names that are not keywords — `print`, `list`, `type`, `id` — are fine: `Cfg.app.print`
works.

Read such a value with item access, and a top-level name with `getattr`:

```python
Cfg.app['class']          # key named with a keyword
Cfg.app['my-key']         # key that is not an identifier
Cfg.app[1]                # non-string key
Cfg.app['items']          # key named like a dict method
getattr(Cfg, 'global')    # config/global.yaml
```

Every time the config loads, PyFlexCfg logs one WARNING listing these names with their paths:

```text
These config names cannot be read with dot notation: app.class (Python keyword), app.items (dict
attribute), app['my-key'] (not an identifier), app[1] (not a string), global (Python keyword). Use
item access instead, for example Cfg.app['items'] rather than Cfg.app.items; for a top-level name
use getattr(Cfg, 'name').
```

Two details:

- A dict-method name at the very top level, such as `config/items.yaml`, is reachable as `Cfg.items`
  and is not reported. Keywords are reported at every level.
- The warning is a log message, so it shows only when your application has logging configured (see
  [Logging](#logging)).

One case cannot be detected at load time. A key that starts with two underscores and does not end
with two (`__token`) works as `Cfg.app.__token` at module level, but inside a class body Python
rewrites the name and the access fails with `AttributeError`. Use `Cfg.app['__token']` there.

**When loading happens.** The configuration is loaded the first time `Cfg` is requested from the
package — in practice, at your `from pyflexcfg import Cfg` line. That is also where a missing config
root or an unsatisfied `!required` key raises. A bare `import pyflexcfg`, or importing only
`AESCipher`, `AttrDict`, `Required` or `Secret`, loads nothing and needs no config directory.

That first load is thread-safe: if several threads request `Cfg` at the same moment, the config is
loaded once and every thread receives the same fully loaded object. Later calls to
`Cfg.reload_config()` and any changes you make to `Cfg` at runtime are not synchronised — guard
those yourself if threads share them.

---

## Configuration root and project root

PyFlexCfg distinguishes two paths:

- **Config root** — the directory it walks for YAML files. Defaults to `./config` relative to the
  current working directory. Override with `PYFLEX_CFG_ROOT_PATH` (absolute path).
- **Project root** — the anchor used by the `!proj_root` YAML constructor. Resolved as follows:
  1. `PYFLEX_PROJECT_ROOT_PATH` env var, if set — used verbatim.
  2. `Path.cwd()` when `PYFLEX_CFG_ROOT_PATH` is **not** set (default layout: `./config` lives
     inside the project root, so cwd *is* the project root).
  3. Otherwise (custom config root, no project-root env var) — **unresolved**. Loading a YAML that
     uses `!proj_root` raises `RuntimeError`. Configs that don't use the tag are unaffected.

**If you set `PYFLEX_CFG_ROOT_PATH`, also set `PYFLEX_PROJECT_ROOT_PATH` whenever your config uses
`!proj_root`.** The default layout requires neither.

---

## `.env` files

A single `*.env` file placed directly inside the config root (not in a subdirectory) is loaded via
[`python-dotenv`](https://pypi.org/project/python-dotenv/) *before* YAML parsing. This lets you set
`PYFLEX_CFG_KEY`, `CFG__…` overrides, and other environment variables without touching the shell.
The file is not parsed as YAML and not exposed as a `Cfg.<name>` attribute. It may have any name
ending in `.env` (`.env`, `app.env`, `secrets.env`).

> **Only one `.env` file is allowed in the config root.**
>
> If PyFlexCfg finds two or more, it stops instead of loading them:
>
> ```text
> RuntimeError: Found 2 .env files in /app/config (app.env, backup.env). Keep exactly one: several
> would load in no guaranteed order, leaving shared variables undefined.
> ```
>
> The reason: several files would be read in whatever order the operating system lists them, which
> can differ between machines. Any variable defined in more than one — a `CFG__*` override,
> `PYFLEX_ENV`, or a credential such as `VAULT_ADDR` and `VAULT_TOKEN` — would end up with an
> unpredictable value.
>
> This applies everywhere `.env` files are read: when `Cfg` first loads, on `Cfg.reload_config()`,
> and in `pyflexcfg encrypt` (with or without `--dry-run`). Nothing is read into the environment
> when the check fails.
>
> A file left behind by accident (`old.env`, `backup.env`, `local.env`) counts. Put all variables in
> one file, and remove or rename any other file ending in `.env`. If you need per-environment
> values, use `PYFLEX_ENV` layers or set the variables in the process environment.
>
> **Upgrading from 2.x:** version 2 loaded every `.env` file it found. If your config root has more
> than one, merge them into a single file before upgrading.

### Order of precedence

When the same setting is given in more than one place, the place lower in this table wins:

| Priority | Source | Notes |
|---|---|---|
| 1 (lowest) | YAML files | The base configuration |
| 2 | The active `PYFLEX_ENV` layer | Deep-merged over the base YAML |
| 3 | `CFG__*` variables set by the process | Shell, container, orchestrator |
| 4 (highest) | `CFG__*` variables in a `.env` file | Replace a process variable of the same name |

**A `.env` file overrides the process environment.** If `PYFLEX_ENV`, a `CFG__*` override or any
other variable is set both by the process and in a `.env` file in the config root, the value from
the file is used. The file's values are written into `os.environ`, so they are also what the rest of
your application sees.

**Three credential variables are the exception: `PYFLEX_CFG_KEY`, `VAULT_ADDR` and `VAULT_TOKEN`.**
For these PyFlexCfg refuses to choose. If the process provides one of them and a `.env` file gives
it a *different* value, loading stops:

```text
RuntimeError: Set by the process and, to a different value, in a .env file: VAULT_ADDR (vault.env).
Define each of these variables in one place only.
```

This protects against a stale file silently replacing an injected `VAULT_TOKEN`, a file pointing a
valid token at another `VAULT_ADDR`, and `pyflexcfg encrypt` encrypting with a different key than
the one your process uses. The rule in full:

| The process provides the variable | A `.env` file sets it | Result |
|---|---|---|
| no | yes | The file's value is used |
| yes | no | The process value is used |
| yes | yes, same value | Fine — nothing to resolve |
| yes | yes, different value | `RuntimeError`; nothing from the `.env` file is applied |

A value that came from a `.env` file in the first place may change in the file later:
`Cfg.reload_config()` picks up a rotated `VAULT_TOKEN` without complaint. The error is only about a
file contradicting something the process itself provides.

For all other variables PyFlexCfg does not detect or resolve a conflict; the file simply wins.
Keeping the sources consistent is up to you:

- Define each variable in one place only. In a deployment where the orchestrator injects
  credentials, do not ship a `.env` file that also sets them.
- Do not commit `.env` files holding secrets, and do not copy a development `.env` into a
  production config root.
- Keep stray `.env` files out of the config root; a second one stops loading (see the note above).

`PYFLEX_CFG_ROOT_PATH` is the one setting a `.env` file cannot provide, because the config root has
to be known before the files inside it can be found.

---

## Environment-variable overrides

Variables matching `CFG__SECTION__KEY` override `Cfg.section.key`. `Cfg.update_from_env()` is called
automatically when `Cfg` loads, but you can call it again at any point (for example, after mutating env vars
in a test). Values are auto-coerced as `int` → `float` → `bool` → `str`. Force a specific type with
a trailing `::Type` suffix:

| Suffix | Result |
|---|---|
| `::int` | Python `int` |
| `::float` | Python `float` |
| `::bool` | `true`/`false` → `bool` |
| `::str` | Force string, no auto-coercion |
| `::Secret` | Wrap as `Secret` (masked in all repr/str/log output) |
| `::yaml_r` | Parse as YAML, **replace** the existing value wholesale |
| `::yaml_m` | Parse as YAML, **merge** into the existing dict (both sides must be dicts) |

Examples:

```dotenv
CFG__DB__PORT=5432                             # int via auto-coercion
CFG__DB__TIMEOUT=2.5                           # float via auto-coercion
CFG__FEATURES__BETA=true                       # bool via auto-coercion
CFG__DB__PASSWORD=hunter2::Secret              # masked Secret
CFG__SERVERS=[host-a, host-b, host-c]::yaml_r  # list — replaces existing
CFG__DB={port: 6543, ssl: true}::yaml_m        # dict — merged into Cfg.db
CFG__DB={port: 6543, ssl: true}::yaml_r        # dict — wipes Cfg.db, writes only these keys
```

`::yaml_m` falls back to replace semantics when either side is not a dict. Overrides for missing
dotted paths are logged at DEBUG level and skipped.

**How a variable name is matched to keys.** Variable names are case-insensitive: the name is
lowercased and split on `__`, and each part is matched against the config keys at that level.

- A key spelled exactly like the lowercase part wins.
- Otherwise a key that differs only in case matches, and keeps its own spelling:
  `CFG__APP__APIKEY=…` updates `apiKey`, and `CFG__APP__DB__PORT=…` updates `DB.Port`.
- If two keys differ only in case and neither is the exact lowercase form (`Host` and `HOST`), the
  variable is ambiguous and loading raises `RuntimeError` naming both keys.
- If the last part matches no key, a new key is created under the lowercase name.

Keys that cannot be spelled in a variable name cannot be overridden this way: a hyphenated key such
as `my-key` (`CFG__APP__MY_KEY` creates a separate `my_key`), a key containing a double underscore,
or a non-string key. Replace the parent mapping with `::yaml_m` or `::yaml_r` instead:
`CFG__APP='{my-key: new}::yaml_m'`.

The path is resolved key by key, so config keys that share a name with a dict method work as
override targets: `CFG__APP__ITEMS__SIZE=5` sets the `size` under a key called `items`. When reading
such a key in code, use item access (`Cfg.app['items']`) — `Cfg.app.items` is the dict method. See
[Names that dot notation cannot reach](#names-that-dot-notation-cannot-reach).

The first path component may not be a name PyFlexCfg itself uses on `Cfg`: one starting with an
underscore, or a handler member (`reload_config`, `apply_env_layer`, `update_from_env`,
`validate_required`, `config_root`, `project_root`). Such a variable, for example
`CFG__RELOAD_CONFIG=…`, raises `RuntimeError` naming it. Paths under `env`
(`CFG__ENV__DEV__REGION=…`) are allowed.

---

## Environment layering (`PYFLEX_ENV`)

Set `PYFLEX_ENV` to the name of an environment tier and PyFlexCfg will **deep-merge** that tier's
config into the root namespace after the base YAML loads. Given:

```text
config/
├── database.yaml        # host: base-db  port: 5432
└── env/
    ├── dev.yaml         # database:\n  host: dev-db
    └── prd.yaml         # database:\n  host: prd-db  port: 5433
```

```shell
PYFLEX_ENV=dev python app.py
```

After `Cfg` loads: `Cfg.database.host == 'dev-db'`, `Cfg.database.port == 5432` (preserved by deep merge).

Priority order (lowest → highest): base YAML → env-layer merge → `CFG__*` env-var overrides. See
[Order of precedence](#order-of-precedence) for the full table, including `.env` files.

Layer values are copied into the root, not shared with it. A `CFG__*` override or a change you make
to the effective config never alters the definition under `Cfg.env.<tier>`.

Tiers are defined only by files in the `env/` directory. A single `config/env.yaml` file is ordinary
config, reachable as `Cfg.env`: it is never merged by `PYFLEX_ENV`, and a `!required` inside it is
validated like any other.

A tier file may be named anything that is a valid config name, including words such as `items` or
`keys`. Its top-level keys, however, become attributes of `Cfg`, so a few names are rejected with a
`RuntimeError` before anything is merged: `env` itself, names starting with an underscore, the
handler's own members (`reload_config`, `apply_env_layer`, `update_from_env`, `validate_required`,
`config_root`, `project_root`), and non-string keys.

If `PYFLEX_ENV` names a tier that doesn't exist, PyFlexCfg logs a DEBUG message and continues
without error — a typo fails silently by design so that missing envs don't crash production.

---

## Required keys (`!required`)

Mark any YAML scalar `!required` to declare it must be provided at runtime:

```yaml
# config/database.yaml
host: !required
port: 5432
password: !required
```

PyFlexCfg raises `RuntimeError` when `Cfg` loads (after all overrides run) if any sentinels remain:

```
RuntimeError: Required config values are missing: ['database.host', 'database.password']
```

Only the effective configuration is validated. The layer definitions under `env/` are not checked
themselves: a `!required` in `env/prd.yaml` matters only when `PYFLEX_ENV=prd` merges it into the
root, where it is reported by its effective path (`database.password`, not
`env.prd.database.password`) and can be satisfied like any other key. A `!required` in a tier that
is not active never blocks loading. The flip side: if you read `Cfg.env.<tier>` directly instead of
activating it, a sentinel there is not caught.

Satisfy required keys with env-var overrides or the env layer before `Cfg` is first imported:

```shell
CFG__DATABASE__HOST=localhost CFG__DATABASE__PASSWORD=hunter2 python app.py
```

`!required` also works inside lists, including on keys of mappings within a list. Such entries are
reported with their index, for example `app.hosts[1]` or `app.servers[0].host`. A list item cannot
be overridden on its own — env-var overrides and the env layer replace a list as a whole — so supply
the complete list:

```shell
CFG__APP__HOSTS='[host-a, host-b]::yaml_r' python app.py
```

The `Required` sentinel class is importable if you need to inspect or inject it programmatically:

```python
from pyflexcfg import Cfg, Required

Cfg.validate_required()  # raises if any Required() sentinels remain
```

---

## Custom YAML constructors

| Tag | Returns | Description |
|---|---|---|
| `!string` | `str` / `Secret` | Join sequence parts as one string; a `Secret` if any part is one. |
| `!encr` | `Secret` | Decrypt a base64 secret using `PYFLEX_CFG_KEY` (AES-GCM v1). |
| `!encr_kdf` | `Secret` | Same but PBKDF2 KDF — slower, higher brute-force resistance. |
| `!required` | `Required` | Raises at startup unless replaced by an override. |
| `!vault` | `Secret` / `AttrDict` of `Secret`s | Fetch from HashiCorp Vault (see [Vault section](#hashicorp-vault)). |
| `!path` | `Path` | Host-native concrete path from the given parts. |
| `!home_dir` | `Path` | Host-native path rooted at the current user's home directory. |
| `!proj_root` | `Path` | Host-native path rooted at the project root (see above). |
| `!path_posix` | `PurePosixPath` | Pure Posix path (legacy alias of `!pure_path_posix`). |
| `!path_win` | `PureWindowsPath` | Pure Windows path (legacy alias of `!pure_path_win`). |
| `!pure_path` | `PurePath` | OS-default pure-flavor path. |
| `!pure_path_posix` | `PurePosixPath` | Explicit Posix-flavor path regardless of host OS. |
| `!pure_path_win` | `PureWindowsPath` | Explicit Windows-flavor path regardless of host OS. |

The "pure" variants let you compose paths targeting a different OS than the host (e.g. building a
Posix path on a Windows host that talks to a remote Unix box).

Examples:

```yaml
greeting: !string ['Hello, ', 'world!']
log_file: !proj_root [logs, app.log]
home_cache: !home_dir [.cache, my-app]
remote_log: !pure_path_posix [/var, log, remote, app.log]
windows_share: !pure_path_win ['C:\', Shares, app]
```

---

## Handling secrets

PyFlexCfg uses **AES-GCM** (authenticated encryption). AES-GCM provides integrity guarantees that
AES-CBC does not — any ciphertext tampering raises `ValueError` at decrypt time rather than silently
producing corrupted plaintext. Two strength levels are available:

| Tag | Key derivation | When to use |
|---|---|---|
| `!encr` | SHA-256 (fast) | Most secrets — API keys, tokens, passwords |
| `!encr_kdf` | PBKDF2HMAC, 480k iters, random salt | Crown-jewel secrets where brute-force resistance matters |

**Encrypt a value:**

```python
import os
from pyflexcfg import AESCipher

aes = AESCipher(os.environ['PYFLEX_CFG_KEY'])
print(aes.encrypt('hunter2'))          # !encr  ciphertext (fast)
print(aes.encrypt_kdf('topsecret'))    # !encr_kdf ciphertext (PBKDF2)
```

Or encrypt every plaintext value in the config tree in-place:

```shell
PYFLEX_CFG_KEY=my-key pyflexcfg encrypt
```

**Use in YAML:**

```yaml
api_key: !encr UEZMWA...
db_pass: !encr_kdf UEZMWA...
```

Every ciphertext starts with the 4-byte marker `PFLX` followed by a version byte, so in base64 it
always begins with `UEZMWA`. The marker is how PyFlexCfg tells its own ciphertexts apart from v2
ones and from plaintext. `AESCipher.is_encrypted(value)` performs the same check and also requires
the value to be complete — long enough to hold its nonce and authentication tag — so a truncated
ciphertext is not mistaken for an encrypted value.

At load time each value decrypts into a `Secret`. `Secret` is a `str` subclass — its `repr`,
`str()`, f-strings, and `%`-format arguments all output `********`. Equality and slicing work
normally on the underlying value.

Both `Secret` and `AESCipher` are importable from the package root:

```python
from pyflexcfg import AESCipher, Secret
```

PyFlexCfg requires `PYFLEX_CFG_KEY` only when at least one `!encr` / `!encr_kdf` value is present.
A key shorter than 32 characters emits a `WARNING`.

### Composing a string that contains a secret

A connection string or an auth header usually needs a secret in the middle of other text. Build it
in YAML with `!string`: the parts may include `!encr`, `!encr_kdf` or `!vault` values.

```yaml
# config/db.yaml
url: !string ['postgresql://app:', !encr UEZMWA..., '@db.example.com:', 5432, '/main']
auth_header: !string ['Bearer ', !vault secret/data/myapp/api#token]
```

```python
from pyflexcfg import Cfg

print(Cfg.db.url)                  # ********
connect(Cfg.db.url)                # receives postgresql://app:hunter2@db.example.com:5432/main
```

When any part is a secret, the whole result is a `Secret`: it holds the real, fully composed value
and is masked wherever it is displayed. With no secret part, `!string` returns a plain `str`.

If you compose in code instead, **do not use an f-string, `format()` or `%`** — formatting a
`Secret` yields its mask. Concatenate or join, and wrap the result if you want it to stay masked:

```python
password = Cfg.db.password         # a Secret holding 'hunter2'

f'postgresql://app:{password}@db'                  # 'postgresql://app:********@db'  — broken
'postgresql://app:' + password + '@db'             # 'postgresql://app:hunter2@db'   — plain str
''.join(['postgresql://app:', password, '@db'])    # 'postgresql://app:hunter2@db'   — plain str
Secret('postgresql://app:' + password + '@db')     # same value, masked again
```

The same applies to any code you hand a `Secret` to: a library that formats or calls `str()` on it
receives the mask, not the value.

Path tags are the exception: `!path` and the other path constructors return ordinary path objects,
which cannot be masked. Do not put a secret in a path.

### Migrating `!encr` from v2

v2 used AES-CBC; v3 switched to AES-GCM. **Old ciphertexts still decrypt** — a value without the
`PFLX` marker is treated as a v2 ciphertext and decrypted transparently. However, every load of a
legacy ciphertext emits a `logging.WARNING` urging migration.

To migrate all values in one step:

```shell
PYFLEX_CFG_KEY=my-key pyflexcfg encrypt
```

For each legacy `!encr` value the command decrypts it with `PYFLEX_CFG_KEY` and writes it back
in the AES-GCM format. After it completes, the warnings disappear and the values are protected by
authenticated encryption. Commit the updated YAML files — no other code changes are needed.
Run `pyflexcfg encrypt --dry-run` first to list the legacy values without touching any file.

A value that has the shape of a legacy ciphertext but does not decrypt with the current key is
**left untouched**, reported as a warning, and makes the command exit 1. This happens when
`PYFLEX_CFG_KEY` is not the key the value was encrypted with, and also for a plaintext secret that
is itself base64 of 32, 48, 64… bytes — the two cannot be told apart. Encrypt such a value manually.

To migrate or encrypt a single value manually:

```python
from pyflexcfg import AESCipher
aes = AESCipher('my-key')
print(aes.encrypt(aes.decrypt_legacy('old-v2-ciphertext')))   # migrate a v2 value
print(aes.encrypt('the-plaintext'))                           # encrypt a plaintext value
```

### Pre-commit hook

Catch unencrypted secrets before they reach version control:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pyflexcfg-encrypt-check
        name: Check for unencrypted config secrets
        entry: pyflexcfg encrypt --dry-run
        language: system
        pass_filenames: false
```

---

## HashiCorp Vault

Install the optional extra:

```shell
pip install "pyflexcfg[vault]"
```

Set `VAULT_ADDR` and `VAULT_TOKEN`, then reference secrets directly in YAML. Set them in one place
only: if the process provides one of them and a `.env` file in the config root gives it a different
value, loading raises an error instead of picking one (see
[Order of precedence](#order-of-precedence)).

```yaml
db_password: !vault secret/data/myapp/db#password   # KV v2 — field
all_creds:   !vault secret/myapp/creds               # KV v1 — whole secret → AttrDict
```

Path format: `mount/path/to/secret#field`. The first segment is always the mount point, for KV v1
and KV v2 alike (`kv/team/app` reads `team/app` from the mount `kv`). The `#field` suffix selects
one key from the secret's data dict; omit it to receive the whole dict as an `AttrDict`.

The KV version is read from the path. If `data/` comes directly after the mount point, the secret is
read as KV v2; anything else is read as KV v1:

| Path | Read as | Mount | Secret path |
|---|---|---|---|
| `secret/data/myapp/db` | KV v2 | `secret` | `myapp/db` |
| `secret/data/team/data/app` | KV v2 | `secret` | `team/data/app` |
| `secret/myapp/db` | KV v1 | `secret` | `myapp/db` |
| `secret/team/data/app` | KV v1 | `secret` | `team/data/app` |

One consequence: a KV v1 secret whose own path starts with `data/` cannot be addressed, because that
spelling always means KV v2.

Everything fetched from Vault is masked. Each leaf value — in a whole secret, or in a field that
holds a nested object or list — becomes a `Secret`, so `repr(Cfg)` and `pyflexcfg show` print
`********` for it. Non-string leaves are stored as the `Secret` of their text (`5432` → `'5432'`),
so convert explicitly where you need the type: `int(Cfg.db.port)`. Do not use `bool()` for that — any
non-empty string is truthy, so compare instead: `Cfg.db.ssl == 'True'`. `null` values stay `None`.

- The Vault client is created on the first `!vault` tag hit, not at import, and then reused. It is
  rebuilt whenever `VAULT_ADDR` or `VAULT_TOKEN` differs from the values it was created with, so
  `Cfg.reload_config()` picks up a rotated token — including one changed in a `.env` file.
- Missing `VAULT_ADDR` or `VAULT_TOKEN` raises `RuntimeError` immediately.
- Missing `hvac` package raises `RuntimeError` with an install hint.
- Network errors or missing secret paths raise `RuntimeError` — startup failure is intentional. The
  error gives the secret path and the kind of failure, e.g.
  `Failed to fetch Vault secret at 'secret/myapp/db' (Forbidden)`. The Vault client's own message is
  left out because it can contain the raw response body.

---

## CLI

After installation, the `pyflexcfg` command (or `python -m pyflexcfg`) is available:

```shell
# Print the effective merged config as YAML (secrets masked as *******)
pyflexcfg show

# Print config root, project root, and active PYFLEX_ENV
pyflexcfg env

# Encrypt plaintext !encr / !encr_kdf values and migrate legacy v2 ciphertexts, in-place
pyflexcfg encrypt

# Report without writing; exit 1 on plaintext or on a non-PBKDF2 value under !encr_kdf (pre-commit hook)
pyflexcfg encrypt --dry-run
```

All commands read `PYFLEX_CFG_ROOT_PATH` and `PYFLEX_CFG_KEY` from the environment. Every command,
`encrypt` included, first loads the `.env` file in the config root, so a `PYFLEX_CFG_KEY` kept
there is picked up. If the process also sets `PYFLEX_CFG_KEY` to a different value, the command
stops with an error and encrypts nothing (see [Order of precedence](#order-of-precedence)). Like
normal loading, every command stops if the config root contains more than one `.env` file.
`encrypt` exits 1
with an error if the config root is missing, is not a directory, or contains no `.yaml` / `.yml`
files, so a misconfigured pre-commit hook fails instead of passing silently. It also rejects any
argument other than `--dry-run` before touching a file, so a mistyped flag such as `--dryrun` cannot
turn a check into a write.

`pyflexcfg encrypt` reads each file with a YAML tokenizer, so it acts only on real `!encr` /
`!encr_kdf` tags. Text that merely mentions `!encr` — inside a string or a comment — is never
touched, and the rest of the file (comments, layout, line endings) is preserved byte for byte.
Plain, quoted and flow-style values are all handled; a quoted value is written back unquoted,
since ciphertext needs no quoting.

The command also checks that a ciphertext matches its tag. Both tags decrypt either kind of
ciphertext at load time, so a value produced by `encrypt()` and pasted under `!encr_kdf` would load
fine while lacking the PBKDF2 protection the tag stands for. `pyflexcfg encrypt` re-encrypts such a
value with PBKDF2, and `--dry-run` reports it and exits 1. The reverse — a PBKDF2 ciphertext under
`!encr` — is stronger than required and is left alone.

What it will not rewrite: a block scalar (`|` or `>`), a value carrying an anchor or alias, a tag
with no value, a legacy-looking value it cannot decrypt, a value that carries the `PFLX` marker but
is truncated or of an unknown version, and any file the tokenizer rejects. Each is
reported on stderr and makes the command exit 1 (with or without `--dry-run`), so encrypt those
manually. Reports give the file, line, tag and key — never the value.

---

## Runtime reload

`Cfg.reload_config(config_path=None, project_root=None, reset=True)` re-walks the configuration tree
and re-runs the full load pipeline (env files, YAML, env-layer merge, env-var overrides, required
validation).

- `config_path` — switch config roots (handy in tests). Defaults to the current `Cfg.config_root`.
- `project_root` — explicit project root for `!proj_root`. When omitted, resolved from env vars.
  Pass this to override without touching the environment (the typical test pattern).
- `reset=True` (default) — first drop every existing config value, whatever put it there: YAML
  files, the env layer, `CFG__*` overrides, or your own assignments to `Cfg`. The result reflects
  only what is on disk and in the environment now, so switching `PYFLEX_ENV` or removing a `CFG__*`
  variable and reloading leaves nothing behind.
- `reset=False` — overlay loaded top-level keys without dropping siblings. Values that came from a
  previous env layer or override, and that the new load does not set, stay as they were.

---

## Logging

PyFlexCfg logs to the `pyflexcfg` logger: load details at DEBUG, and a few things you should act on
at WARNING — a legacy ciphertext that needs migrating, a short encryption key, and config names that
dot notation cannot reach (see
[Names that dot notation cannot reach](#names-that-dot-notation-cannot-reach)).

Like most libraries, PyFlexCfg attaches no output handler of its own, so **none of these messages
appear unless your application configures logging**. Do that before `Cfg` is first imported:

```python
import logging

logging.basicConfig(level=logging.WARNING)             # shows PyFlexCfg's warnings
logging.getLogger('pyflexcfg').setLevel(logging.DEBUG)  # optional: load details too

from pyflexcfg import Cfg
```

PyFlexCfg keeps secret values out of its own log messages and out of the errors it raises for
encryption, decryption and env-var overrides. A failed override conversion, for instance, names the
variable and the target type but not the value:
`CFG__DB__PASSWORD: value could not be cast as 'int' (ValueError)`.

A YAML syntax error in a config file is reported with the file path, line and column only; the
offending line itself is not quoted.

Two limits to keep in mind:

- `str(Cfg)` and `pyflexcfg show` mask only `Secret` values, so anything you want hidden there must
  be a `Secret` (`!encr`, `!encr_kdf`, `!vault` or the `::Secret` suffix).
- A `Secret` masks how it is *displayed* — `repr`, `str`, every kind of string formatting, and
  PyFlexCfg's own YAML output. It is still a `str`, so code that serialises or combines it gets the
  real value: `json.dumps`, `yaml.dump` with PyYAML's default dumper, `','.join(...)`, slicing and
  concatenation. Treat those results as sensitive.

---

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```shell
uv sync                                # install dependencies
uv run pytest                          # run the test suite
uv run pytest tests/test_handler.py    # run a single file
uv run ruff check .                    # lint
uv run ruff format .                   # format
uv build                               # produce wheel + sdist in dist/
```
