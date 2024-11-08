import sys
from pathlib import Path
from typing import AnyStr, Sequence

import yaml

from .constants import ROOT_CONFIG_DIR_NAME
from .misc import AttrDict
from .yaml_loader import YamlLoader


class HandlerMeta(type):
    """
    Makes Handler load values while being imported, so no additional initialization is required.
    """
    config_root = Path.cwd() / ROOT_CONFIG_DIR_NAME
    os_type = sys.platform

    def __new__(cls, name, bases, namespace):
        init_attrs = AttrDict(namespace)
        cls.load_config(cls.config_root, init_attrs)
        return super().__new__(cls, name, bases, init_attrs)

    def __str__(cls):
        """ Pretty prints current settings. """
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

        for item in config_path.iterdir():
            if item.is_dir():
                dct[item.name] = AttrDict()
                cls.load_config(item, dct[item.name])

            if item.suffix in ('.yml', '.yaml'):
                cls._load_yaml_from_file(dct, item)

    @classmethod
    def _load_yaml_from_file(cls, dct: AttrDict | object, file: Path) -> None:
        with file.open() as cfg_file:
            data = cls.to_attrdict(yaml.load(cfg_file, YamlLoader))
            setattr(dct, file.stem, data)
