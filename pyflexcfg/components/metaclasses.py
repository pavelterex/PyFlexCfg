from __future__ import annotations

import keyword
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from . import logger
from .constants import (
    ENCRYPTION_KEY_ENV_VAR,
    NAME_REGEX_STRING,
    PROJECT_ROOT_PATH_ENV,
    ROOT_CONFIG_DIR_NAME,
    ROOT_CONFIG_PATH_ENV,
)
from .misc import AttrDict
from .yaml_dumper import YamlDumper
from .yaml_loader import YamlLoader

_NAME_RE = re.compile(NAME_REGEX_STRING)
# Credentials a `.env` file may supply or repeat, but not contradict when the process already provides them.
_PROTECTED_ENV_VARS = frozenset({ENCRYPTION_KEY_ENV_VAR, 'VAULT_ADDR', 'VAULT_TOKEN'})
# Class attributes `reload_config` assigns that are not config values.
_RESERVED_ATTRS = frozenset({'config_root', 'project_root'})
# Key names that attribute access on an `AttrDict` resolves to its own method or dunder instead of the value.
_SHADOWED_KEYS = frozenset(dir(AttrDict))

# Values this module wrote into the environment from `.env` files, by normalised variable name.
_env_file_values: dict[str, str] = {}


class HandlerMeta(type):
    """
    Metaclass that loads the YAML configuration tree at class-creation time.

    Resolves the config root from `PYFLEX_CFG_ROOT_PATH` (falling back to
    `<cwd>/config`), loads any `*.env` files non-recursively from that root
    via `python-dotenv`, then walks the tree and assigns each YAML file's
    contents as nested attributes on the class namespace. Directory and file
    names that don't match :data:`NAME_REGEX_STRING` are silently skipped.
    """

    config_root = Path(os.getenv(ROOT_CONFIG_PATH_ENV, Path.cwd() / ROOT_CONFIG_DIR_NAME))
    project_root: Path | None = None

    def __new__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]) -> HandlerMeta:
        init_attrs = AttrDict(namespace)
        init_attrs['_handler_attrs'] = frozenset(namespace) | _RESERVED_ATTRS

        if not cls.config_root.exists():
            raise RuntimeError(f'Configuration root path {cls.config_root} is not found!')

        cls.load_env_files(cls.config_root)
        cls.project_root = cls.resolve_project_root()
        YamlLoader.project_root = cls.project_root

        loaded = AttrDict()
        cls.load_config(cls.config_root, loaded)
        cls.check_root_names(loaded, init_attrs['_handler_attrs'])
        cls.warn_unreachable_keys(loaded)
        init_attrs.update(loaded)

        return super().__new__(cls, name, bases, init_attrs)

    def __str__(cls) -> str:
        """Return the current configuration formatted as YAML."""
        dct = {key: cls.__dict__[key] for key in cls._config_keys()}
        return yaml.dump(dct, Dumper=YamlDumper, indent=4, default_flow_style=False, sort_keys=False)

    @classmethod
    def check_root_names(cls, names: Iterable[str], handler_attrs: frozenset[str]) -> None:
        """Raise `RuntimeError` if a top-level config name would replace a member of the handler class."""
        if conflicts := sorted(handler_attrs.intersection(names)):
            raise RuntimeError(f'Namespace conflict: {conflicts} would replace members of the config handler')

    @classmethod
    def load_config(cls, config_path: Path, dct: AttrDict) -> None:
        """
        Recursively load YAML files under `config_path` into `dct`.

        Directory and file names that don't match :data:`NAME_REGEX_STRING` are
        silently skipped (with a DEBUG log line). Names that *do* match but
        collide with an already-loaded sibling raise `RuntimeError`.

        Args:
            config_path: Directory to walk.
            dct: Target `AttrDict` to populate.

        Raises:
            RuntimeError: When a directory or file name collides with an
                already-assigned key.
        """
        if not config_path.is_dir():
            raise RuntimeError(f'{config_path} must be a path to a directory!')

        for item in config_path.iterdir():
            match item:
                case _ if item.is_dir():
                    if not _NAME_RE.match(item.name):
                        logger.debug('Skipping directory %r: name does not match NAME_REGEX_STRING', item.name)
                        continue
                    if item.name in dct:
                        raise RuntimeError(f'Namespace conflict: "{item.name}" is already defined')
                    dct[item.name] = AttrDict()
                    cls.load_config(item, dct[item.name])
                case _ if item.is_file() and item.suffix in {'.yml', '.yaml'}:
                    cls._load_yaml_from_file(dct, item)
                case _ if item.is_file() and item.suffix == '.env':
                    continue  # already handled by load_env_files
                case _:
                    logger.debug('Skipping unsupported item: %s', item)

    @classmethod
    def load_env_files(cls, config_path: Path) -> None:
        """
        Load the `*.env` file directly inside `config_path` into the environment.

        At most one such file may exist. Its values replace variables the process
        already set, with one exception: for the credential variables in
        `_PROTECTED_ENV_VARS` a different value in the file is refused, so neither
        source silently wins.

        Raises:
            RuntimeError: More than one `.env` file is present, or the file gives a
                protected variable a value that differs from the one the process
                provides. Nothing is read into the environment in either case.
        """
        if not config_path.is_dir():
            return

        env_files = sorted(item for item in config_path.iterdir() if item.is_file() and item.suffix == '.env')
        if len(env_files) > 1:
            names = ', '.join(item.name for item in env_files)
            raise RuntimeError(
                f'Found {len(env_files)} .env files in {config_path} ({names}). Keep exactly one: '
                'several would load in no guaranteed order, leaving shared variables undefined.',
            )

        for env_file in env_files:
            values = dotenv_values(env_file)
            conflicts = sorted(name for name, value in values.items() if _contradicts_process(name, value))
            if conflicts:
                raise RuntimeError(
                    'Set by the process and, to a different value, in a .env file: '
                    f'{", ".join(f"{name} ({env_file.name})" for name in conflicts)}. '
                    'Define each of these variables in one place only.',
                )

            for name, value in values.items():
                if value is not None:
                    os.environ[name] = value
                    _env_file_values[_env_name(name)] = value
            logger.debug('Loaded env file: %s', env_file)

    @classmethod
    def resolve_project_root(cls, custom_root: bool = False) -> Path | None:
        """
        Resolve the project root from environment variables.

        Precedence:
            1. `PYFLEX_PROJECT_ROOT_PATH` if set — used verbatim.
            2. `Path.cwd()` when neither `PYFLEX_CFG_ROOT_PATH` nor
               `custom_root` signals a non-default config location (default
               layout: `./config` sits inside the project root).
            3. `None` otherwise — `!proj_root` raises at parse time; configs
               that don't use the tag are unaffected.

        Args:
            custom_root: Pass `True` when the config path was supplied
                explicitly (e.g. via the `config_path` kwarg of
                `reload_config`). Suppresses the `Path.cwd()` fallback so
                that callers in non-default layouts must provide an explicit
                project root.

        Returns:
            The resolved project root, or `None` if it cannot be inferred.
        """
        if explicit := os.getenv(PROJECT_ROOT_PATH_ENV):
            return Path(explicit)

        if not custom_root and not os.getenv(ROOT_CONFIG_PATH_ENV):
            return Path.cwd()

        return None

    @classmethod
    def to_attrdict(cls, data: Any) -> Any:
        """Wrap nested `dict` in :class:`AttrDict`; pass lists/tuples through."""
        if isinstance(data, dict):
            return AttrDict({key: cls.to_attrdict(value) for key, value in data.items()})

        if isinstance(data, list):
            return [cls.to_attrdict(item) for item in data]

        if isinstance(data, tuple):
            return tuple(cls.to_attrdict(item) for item in data)

        return data

    @classmethod
    def warn_unreachable_keys(cls, tree: Mapping[Any, Any]) -> None:
        """
        Log one WARNING listing every name in `tree` that dot notation cannot reach.

        Covers Python keywords, non-identifiers, non-string keys and, below the top
        level, names that resolve to a dict attribute. Top-level names become class
        attributes, so a dict-attribute name there is reachable and not reported.
        """
        entries = sorted(_unreachable_entries(tree, '', top_level=True))

        if entries:
            logger.warning(
                'These config names cannot be read with dot notation: %s. Use item access instead, for example '
                "Cfg.app['items'] rather than Cfg.app.items; for a top-level name use getattr(Cfg, 'name').",
                ', '.join(entries),
            )

    def _config_keys(cls) -> list[str]:
        """Names of the class attributes that hold config values, not handler machinery."""
        return [key for key in cls.__dict__ if not key.startswith('_') and key not in cls._handler_attrs]

    @classmethod
    def _load_yaml_from_file(cls, dct: AttrDict, file: Path) -> None:
        if not _NAME_RE.match(file.stem):
            logger.debug('Skipping file %r: stem does not match NAME_REGEX_STRING', file.name)
            return

        if file.stem in dct:
            raise RuntimeError(f'Namespace conflict: "{file.stem}" is already defined')

        # Pass the open file, not its text: PyYAML quotes the offending line in errors only for str input.
        with file.open() as cfg_file:
            data = cls.to_attrdict(yaml.load(cfg_file, YamlLoader))

        dct[file.stem] = data
        logger.debug('Loaded configuration file: %s', file)


def _child_path(path: str, key: Any) -> str:
    """Extend `path` with `key`: dotted for an identifier, bracketed otherwise."""
    if isinstance(key, str) and key.isidentifier():
        return f'{path}.{key}' if path else key

    return f'{path}[{key!r}]'


def _contradicts_process(name: str, file_value: str | None) -> bool:
    """Tell whether a `.env` value for a protected variable differs from one the process provides."""
    current = os.environ.get(name)
    if _env_name(name) not in _PROTECTED_ENV_VARS or file_value is None or current is None:
        return False

    # A value this module wrote from an earlier `.env` load is the file's own and may change.
    return current != file_value and _env_file_values.get(_env_name(name)) != current


def _env_name(name: str) -> str:
    """Normalise a variable name the way the OS compares it: case-insensitively on Windows."""
    return name.upper() if os.name == 'nt' else name


def _unreachable_entries(value: Any, path: str, *, top_level: bool = False) -> Iterator[str]:
    """Yield `path (reason)` for every key under `value` that dot notation cannot reach."""
    match value:
        case dict():
            for key, item in value.items():
                child = _child_path(path, key)

                if reason := _unreachable_reason(key, top_level=top_level):
                    yield f'{child} ({reason})'

                yield from _unreachable_entries(item, child)
        case list() | tuple():
            for index, item in enumerate(value):
                yield from _unreachable_entries(item, f'{path}[{index}]')


def _unreachable_reason(key: Any, *, top_level: bool) -> str | None:
    """Say why `key` cannot be read as an attribute, or return `None` if it can."""
    if not isinstance(key, str):
        return 'not a string'

    if keyword.iskeyword(key):
        return 'Python keyword'

    if not key.isidentifier():
        return 'not an identifier'

    if not top_level and key in _SHADOWED_KEYS:
        return 'dict attribute'

    return None
