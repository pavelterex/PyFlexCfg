# PyFlexCfg

Flexible YAML configuration handler for Python projects. PyFlexCfg loads a directory tree of YAML files
into a single global `Cfg` object at import time, with support for environment-variable overrides,
encrypted secrets, custom path constructors, and automatic `.env` loading.

## Installation

```shell
pip install pyflexcfg
```

## Quick start

Given this layout:

```text
project/
├── config/
│   ├── general.yaml
│   └── env/
│       ├── dev.yaml
│       └── prd.yaml
```

with each file containing `data: test`, you can use the configuration immediately after import:

```python
from pyflexcfg import Cfg

print(Cfg.general.data)
print(Cfg.env.dev.data)
print(Cfg.env.prd.data)
```

Directory and file names must be valid Python identifiers — they become attribute names on `Cfg`.

## Configuration root and project root

PyFlexCfg distinguishes two paths:

- **Config root** — the directory it walks for YAML files. Defaults to `./config` relative to the
  current working directory. Override with `PYFLEX_CFG_ROOT_PATH` (absolute path).
- **Project root** — the anchor used by the `!proj_root` YAML constructor. Resolved as follows:
  1. `PYFLEX_PROJECT_ROOT_PATH` env var, if set — used verbatim.
  2. `Path.cwd()` when `PYFLEX_CFG_ROOT_PATH` is **not** set (default layout: `./config` lives
     inside the project root, so cwd *is* the project root).
  3. Otherwise (custom config root, no project-root env var) — **unresolved**. Loading a YAML that
     uses `!proj_root` will raise `RuntimeError`. Configs that don't use the tag are unaffected.

In short: **if you set `PYFLEX_CFG_ROOT_PATH`, you must also set `PYFLEX_PROJECT_ROOT_PATH`
whenever your config uses `!proj_root`.** The default layout requires neither.

## Environment-variable overrides

Variables matching `CFG__SECTION__KEY` override `Cfg.section.key`. `Cfg.update_from_env()` is called
automatically at import, but you can call it again at any point (for example, after mutating env vars in
a test). Values are auto-coerced as `int` → `float` → `bool` → `str`. Force a specific type with a
trailing `::Type` suffix:

| Suffix      | Result                                                                            |
|-------------|-----------------------------------------------------------------------------------|
| `::int`     | Python `int`                                                                      |
| `::float`   | Python `float`                                                                    |
| `::bool`    | `true`/`false` → `bool`                                                           |
| `::str`     | Force string, no auto-coercion                                                    |
| `::Secret`  | Wrap as `Secret` (masked in logs/repr)                                            |
| `::yaml_r`  | Parse as YAML, **replace** the existing value wholesale (works for any YAML type) |
| `::yaml_m`  | Parse as YAML, **merge** into the existing dict (only when both sides are dicts)  |

Examples:

```dotenv
CFG__DB__PORT=5432                             # int via auto-coercion
CFG__DB__TIMEOUT=2.5                           # float via auto-coercion
CFG__FEATURES__BETA=true                       # bool via auto-coercion
CFG__DB__PASSWORD=hunter2::Secret              # masked Secret
CFG__SERVERS=[host-a, host-b, host-c]::yaml_r  # list — replaces existing
CFG__DB={port: 6543, ssl: true}::yaml_m        # dict — merged into Cfg.db
CFG__DB={port: 6543, ssl: true}::yaml_r        # dict — wipes Cfg.db and writes only these two keys
```

`::yaml_m` falls back to replace semantics when either side is not a dict (you can't merge a list into a
mapping). Overrides for missing dotted paths are logged at DEBUG level and skipped.

## `.env` files

Any `*.env` file found directly inside `PYFLEX_CFG_ROOT_PATH` (non-recursive) is loaded via
`python-dotenv` *before* YAML parsing. This lets you set both `PYFLEX_CFG_KEY` and any `CFG__…`
overrides without touching the shell environment. `.env` files are not parsed as YAML and not exposed
as `Cfg.<name>` attributes.

## Custom YAML constructors

Use these tags inside any YAML file:

| Tag                  | Returns           | Description                                              |
|----------------------|-------------------|----------------------------------------------------------|
| `!string`            | `str`             | Join sequence parts as one string.                       |
| `!encr`              | `Secret`          | Decrypt a base64 secret using `PYFLEX_CFG_KEY`.          |
| `!path`              | `Path`            | Host-native concrete path from the given parts.          |
| `!home_dir`          | `Path`            | Host-native path rooted at the current user's home.      |
| `!proj_root`         | `Path`            | Host-native path rooted at the project root (see above). |
| `!path_posix`        | `PurePosixPath`   | Pure Posix path (legacy alias of `!pure_path_posix`).    |
| `!path_win`          | `PureWindowsPath` | Pure Windows path (legacy alias of `!pure_path_win`).    |
| `!pure_path`         | `PurePath`        | OS-default pure-flavor path.                             |
| `!pure_path_posix`   | `PurePosixPath`   | Explicit Posix-flavor path regardless of host OS.        |
| `!pure_path_win`     | `PureWindowsPath` | Explicit Windows-flavor path regardless of host OS.      |

The "pure" variants exist so users on one OS can compose paths that target another OS (e.g. building a
Posix path inside config that runs on a Windows host that talks to a remote Unix box). PyFlexCfg never
auto-resolves a `!pure_path_*` to the local flavor — you asked for it, you get it.

Examples:

```yaml
greeting: !string ['Hello, ', 'world!']
log_file: !proj_root [logs, app.log]
home_cache: !home_dir [.cache, my-app]
remote_log: !pure_path_posix [/var, log, remote, app.log]
windows_share: !pure_path_win ['C:\', Shares, app]
```

## Handling secrets

Sensitive values must be encrypted before being committed.

Encrypt:

```python
import os
from pyflexcfg import AESCipher

aes = AESCipher(os.environ['PYFLEX_CFG_KEY'])
ciphertext = aes.encrypt('hunter2')
print(ciphertext)  # 'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI'
```

`encrypt()` returns a base64 ASCII **string** — paste it directly into YAML, no quoting needed:

```yaml
my_secret: !encr A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI
```

At load time PyFlexCfg decrypts the value into a `Secret`, whose `repr`/`str`/`format` outputs are all
masked as `********`. Equality, slicing, and other `str` methods still work on the underlying value.

PyFlexCfg requires `PYFLEX_CFG_KEY` only when at least one `!encr` value is loaded; if all your config
is plain text, the variable is not needed.

## Runtime reload

`Cfg.reload_config(path=None, project_root=None, reset=True)` re-walks the configuration tree.

- `path` — switch config roots (handy for tests). Defaults to the current `Cfg.config_root`.
- `project_root` — explicit project root for the `!proj_root` constructor. When omitted, the value
  is resolved from env vars per the rule above. Pass this to override without touching the
  environment (the typical test pattern).
- `reset=False` — overlay loaded top-level keys onto the existing configuration without dropping
  siblings.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```shell
uv sync                          # install dependencies
uv run pytest                    # run the test suite
uv run pytest tests/test_loader.py  # run a single file
uv run ruff check .              # lint
uv run ruff format .             # format
uv build                         # produce wheel + sdist in dist/
```
