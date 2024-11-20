import os

from .components import log
from .components.metaclasses import HandlerMeta
from .components.misc import AttrDict, Secret


class ConfigHandler(AttrDict, metaclass=HandlerMeta):

    @classmethod
    def update_from_env(cls) -> None:
        """ Override existing config values with ones loaded from env variables. """

        for var_name, var_value in os.environ.items():
            var_name = var_name.lower()

            if var_name.startswith('cfg__'):
                var_value = cls._convert_value_type(var_value)

                dct_keys = var_name.split('__')[1:]
                current = cls
                for key in dct_keys[:-1]:
                    try:
                        current = getattr(current, key)
                    except AttributeError:
                        log.error(f'Key "{key}" is not found. Skipping override by "{var_name.upper()}"')
                        current = None
                        break
                try:
                    current[dct_keys[-1]] = var_value
                except TypeError:
                    if current is not None:
                        log.error(
                            f'Key "{dct_keys[-1]}" could not be assigned. Skipping override by "{var_name.upper()}"'
                        )

    @staticmethod
    def _convert_value_type(src_value: str) -> int | float | bool | str | Secret:
        """
        Convert the string representation of the source value to one of builtin types or Secret.

        The type of the target value could be specified explicitly via :: notation within the src_value.
        For example, strings that are supposed to be stored as a Secret should have explicit type specified like:
        CFG__APP__OPTION=some_string_value::Secret

        Only existing builtin types + Secret are available for conversion.

        Source values without any type specified will get auto-converted to any of simple types: int, float or bool.
        If the auto-conversion is not succeeded - the original (string) representation is returned.

        :param src_value: source value to be converted
        """
        # process values having explicit type specified
        allowed_types = ('Secret', 'int', 'float', 'bool', 'str')

        if '::' in src_value:
            value, value_type = src_value.split('::', 1)

            if value_type not in allowed_types:
                msg = (f'Specified type "{value_type}" is not in the list of allowed types!'
                       f'Value "{value}" will be processed with auto-conversion')
                log.warn(msg)
                src_value = value
            else:
                try:
                    return eval(value_type)(value)
                except ValueError:
                    log.debug(f'Value "{value}" could not be casted as "{value_type}"')

        # process auto-conversion to int or float
        for item in (int, float):
            try:
                return item(src_value)
            except ValueError:
                log.debug(f'Value "{src_value}" could not be casted as "{item}"')

        # process auto-conversion to bool
        if (var_lower := src_value.lower()) in ('true', 'false'):
            return eval(var_lower.capitalize())

        return src_value
