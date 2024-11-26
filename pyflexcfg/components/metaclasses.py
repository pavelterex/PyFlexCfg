import os
import re
from pathlib import Path
from typing import AnyStr, Sequence

import yaml

from . import logger
from .constants import NAME_REGEX_STRING, ROOT_CONFIG_DIR_NAME, ROOT_CONFIG_PATH_ENV
from .misc import AttrDict
from .yaml_loader import YamlLoader


class HandlerMeta(type):
    """
    Metaclass for Config Handler class.

    General purpose is to load values from existing configuration files while being imported,
    so no additional initialization is required.
    """

    config_root = Path(os.getenv(ROOT_CONFIG_PATH_ENV, Path.cwd() / ROOT_CONFIG_DIR_NAME))

    def __new__(cls, name, bases, namespace):
        init_attrs = AttrDict(namespace)

        if not cls.config_root.exists():
            raise RuntimeError(f'Configuration root path {cls.config_root} is not found!')

        cls._load_config(cls.config_root, init_attrs)
        return super().__new__(cls, name, bases, init_attrs)

    def __str__(cls):
        """ Pretty print current settings. """
        dct = {k: v for k, v in list(cls.__dict__.items()) if not k.startswith('_') and not callable(getattr(cls, k))}
        return str(dct)

    @classmethod
    def _to_attrdict(cls, data: AnyStr | AttrDict | Sequence) -> AnyStr | AttrDict | Sequence:
        if isinstance(data, dict):
            for key, value in data.items():
                data[key] = cls._to_attrdict(value)
            data = AttrDict(**data)

        elif isinstance(data, list | tuple):
            for index, item in enumerate(data):
                data[index] = cls._to_attrdict(item)

        return data

    @classmethod
    def _load_config(cls, config_path: Path, dct: AttrDict) -> None:
        """
        Traverse root config dir recursively and update given AttrDict with loaded YAML files' values.

        :param config_path: root directory of configuration
        :param dct: AttrDict instance to be updated with loaded values
        """
        if not config_path.is_dir():
            raise AttributeError(f'{config_path} must be a path to directory!')

        for item in config_path.iterdir():
            match item:
                case _ if item.is_dir() and re.match(re.compile(NAME_REGEX_STRING), item.name):
                    dct[item.name] = AttrDict()
                    cls._load_config(item, dct[item.name])
                case _ if item.is_file() and item.suffix in {'.yml', '.yaml'}:
                    cls._load_yaml_file(dct, item)
                case _:
                    if item.is_dir():
                        logger.error(f'Directory "{item.name}" is not valid for namespace assignment!')
                    elif item.is_file():
                        logger.error(f'File "{item.name}" is not a supported configuration file!')
                    else:
                        logger.warning(f'Unknown item "{item.name}" skipped.')

    @classmethod
    def _load_yaml_file(cls, dct: AttrDict | object, file: Path) -> None:
        with file.open() as cfg_file:
            data = cls._to_attrdict(yaml.load(cfg_file, YamlLoader))
            setattr(dct, file.stem, data)
            logger.debug(f'Configuration from the file "{file}" has been successfully loaded')
