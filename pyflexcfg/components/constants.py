# Env var holding the AES key used by the !encr YAML constructor.
ENCRYPTION_KEY_ENV_VAR = 'PYFLEX_CFG_KEY'

# Valid identifier regex for loaded directory/file/attribute names. Items whose name
# does not match are silently skipped during the config-tree walk.
NAME_REGEX_STRING = r'^[a-z][a-z0-9_]{0,28}[a-z0-9]$'

# Env var that explicitly anchors the project root. Required when
# ROOT_CONFIG_PATH_ENV is set and !proj_root is used; ignored otherwise
# (project root defaults to cwd).
PROJECT_ROOT_PATH_ENV = 'PYFLEX_PROJECT_ROOT_PATH'

# Default directory name searched for under cwd when no explicit config root is given.
ROOT_CONFIG_DIR_NAME = 'config'

# Env var that overrides the config-root path. When set,
# PROJECT_ROOT_PATH_ENV becomes mandatory for any config that uses the
# !proj_root YAML constructor.
ROOT_CONFIG_PATH_ENV = 'PYFLEX_CFG_ROOT_PATH'
