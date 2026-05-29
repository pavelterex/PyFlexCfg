from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from . import logger
from .constants import NAME_REGEX_STRING, PROJECT_ROOT_PATH_ENV, ROOT_CONFIG_DIR_NAME, ROOT_CONFIG_PATH_ENV
from .misc import AttrDict
from .yaml_dumper import YamlDumper
from .yaml_loader import YamlLoader

_NAME_RE = re.compile(NAME_REGEX_STRING)


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

        if not cls.config_root.exists():
            raise RuntimeError(f'Configuration root path {cls.config_root} is not found!')

        cls.project_root = cls.resolve_project_root()
        YamlLoader.project_root = cls.project_root

        cls.load_env_files(cls.config_root)
        cls.load_config(cls.config_root, init_attrs)

        return super().__new__(cls, name, bases, init_attrs)

    def __str__(cls) -> str:
        """Return the current configuration formatted as YAML."""
        dct = {k: v for k, v in cls.__dict__.items() if not k.startswith('_') and not callable(getattr(cls, k))}
        return yaml.dump(dct, Dumper=YamlDumper, indent=4, default_flow_style=False, sort_keys=False)

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
        """Load any `*.env` file in `config_path` (non-recursive) via dotenv."""
        if not config_path.is_dir():
            return

        for item in config_path.iterdir():
            if item.is_file() and item.suffix == '.env':
                load_dotenv(item, override=True)
                logger.debug('Loaded env file: %s', item)

    @classmethod
    def resolve_project_root(cls) -> Path | None:
        """
        Resolve the project root from environment variables.

        Precedence:
            1. `PYFLEX_PROJECT_ROOT_PATH` if set — used verbatim.
            2. `Path.cwd()` when `PYFLEX_CFG_ROOT_PATH` is **not** set
               (default layout: `./config` sits inside the project root).
            3. `None` when `PYFLEX_CFG_ROOT_PATH` is set but no explicit
               project root is provided. `!proj_root` raises in this case;
               configs that don't use the tag are unaffected.

        Returns:
            The resolved project root, or `None` if it cannot be inferred.
        """
        if explicit := os.getenv(PROJECT_ROOT_PATH_ENV):
            return Path(explicit)

        if not os.getenv(ROOT_CONFIG_PATH_ENV):
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
    def _load_yaml_from_file(cls, dct: AttrDict, file: Path) -> None:
        if not _NAME_RE.match(file.stem):
            logger.debug('Skipping file %r: stem does not match NAME_REGEX_STRING', file.name)
            return

        if file.stem in dct:
            raise RuntimeError(f'Namespace conflict: "{file.stem}" is already defined')

        with file.open() as cfg_file:
            data = cls.to_attrdict(yaml.load(cfg_file, YamlLoader))

        dct[file.stem] = data
        logger.debug('Loaded configuration file: %s', file)
