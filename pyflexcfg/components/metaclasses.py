import os
from pathlib import Path
from typing import AnyStr, Sequence

import yaml

from .constants import ROOT_CONFIG_DIR_NAME, ROOT_CONFIG_PATH_ENV
from .misc import AttrDict
from .yaml_loader import YamlLoader


class HandlerMeta(type):
    """
    Metaclass for Config Handler class.

    General purpose is to load values from existing configuration files while being imported,
    so no additional initialization is required.
    """
    config_root = os.getenv(ROOT_CONFIG_PATH_ENV, Path.cwd() / ROOT_CONFIG_DIR_NAME)

    def __new__(cls, name, bases, namespace):
        init_attrs = AttrDict(namespace)

        if not cls.config_root.exists():
            raise RuntimeError(f'Configuration root path {cls.config_root} is not found!')

        cls.load_config(cls.config_root, init_attrs)
        return super().__new__(cls, name, bases, init_attrs)

    def __str__(cls):
        """ Pretty print current settings. """
        dct = {k: v for k, v in list(cls.__dict__.items()) if not k.startswith('_') and not callable(getattr(cls, k))}
        return str(dct)

    @classmethod
    def to_attrdict(cls, data: AnyStr | AttrDict | Sequence) -> AnyStr | AttrDict | Sequence:
        if isinstance(data, dict):
            for key, value in data.items():
                data[key] = cls.to_attrdict(value)
            data = AttrDict(**data)

        elif isinstance(data, list | tuple):
            for index, item in enumerate(data):
                data[index] = cls.to_attrdict(item)

        return data

    @classmethod
    def load_config(cls, config_path: Path, dct: AttrDict) -> None:
        """
        Traverse root config dir recursively and update given AttrDict with loaded YAML files' values.

        :param config_path: root directory of configuration
        :param dct: AttrDict instance to be updated with loaded values
        """
        for item in config_path.iterdir():
            if item.is_dir():
                try:
                    dct[item.name] = AttrDict()
                except KeyError:
                    raise RuntimeError(f'Directory "{item.name}" is not valid for namespace assignment!')
                cls.load_config(item, dct[item.name])

            if item.suffix in ('.yml', '.yaml'):
                cls._load_yaml_from_file(dct, item)

    @classmethod
    def _load_yaml_from_file(cls, dct: AttrDict | object, file: Path) -> None:
        with file.open() as cfg_file:
            data = cls.to_attrdict(yaml.load(cfg_file, YamlLoader))
            setattr(dct, file.stem, data)
