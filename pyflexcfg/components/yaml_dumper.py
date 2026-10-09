from pathlib import PurePath
from typing import Any

from yaml import MappingNode, SafeDumper, ScalarNode

from .misc import AttrDict, Secret


class YamlDumper(SafeDumper):
    """Custom YAML dumper that knows how to serialize PyFlexCfg's types."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        def represent_attr_dict(dumper: YamlDumper, value: AttrDict) -> MappingNode:
            return dumper.represent_mapping('tag:yaml.org,2002:map', value.as_dict())

        def represent_other(dumper: YamlDumper, value: Any) -> ScalarNode:
            return dumper.represent_scalar('tag:yaml.org,2002:str', repr(value))

        def represent_path(dumper: YamlDumper, value: PurePath) -> ScalarNode:
            return dumper.represent_scalar('tag:yaml.org,2002:str', str(value))

        def represent_secret(dumper: YamlDumper, value: Secret) -> ScalarNode:
            return dumper.represent_scalar('tag:yaml.org,2002:str', repr(value))

        # `None` is PyYAML's slot for types with no representer; SafeDumper raises there by default.
        self.add_representer(None, represent_other)
        self.add_representer(AttrDict, represent_attr_dict)
        self.add_representer(Secret, represent_secret)
        self.add_multi_representer(PurePath, represent_path)

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:  # noqa: ARG002
        """Force block-style list indentation (`indentless` is always `False`)."""
        super().increase_indent(flow, False)

    def represent_data(self, data: Any) -> Any:
        # Treat AttrDict before SafeDumper's plain-dict branch can catch it.
        if isinstance(data, AttrDict):
            return self.represent_mapping('tag:yaml.org,2002:map', data.as_dict())

        return super().represent_data(data)
