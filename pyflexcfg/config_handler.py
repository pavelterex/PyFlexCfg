import os

from components.metaclasses import HandlerMeta
from components.misc import AttrDict


class ConfigHandler(AttrDict, metaclass=HandlerMeta):

    @classmethod
    def update_from_env_vars(cls) -> None:
        for var_name, var_value in os.environ.items():
            var_name = var_name.lower()

            if var_name.startswith('cfg__'):
                var_name = var_name.replace('cfg__', 'cls.', 1).replace('__', '.')

                # try to identify whether the value is boolean or not before putting it in Cfg
                if (var_lower := var_value.lower()) in ('true', 'false'):
                    exec(f'{var_name} = bool({var_lower.capitalize()})')  # as bool
                else:
                    exec(f'{var_name} = "{var_value}"')  # as str
