# PyFlexCfg

Flexible configuration handler for Python projects.

### Description

**PyFlexCfg** allows you to store your project's configuration in YAML files and seamlessly load them as a unified object 
when imported into your Python code.

### Features:

- **YAML-based config**: Organize your project's settings using easy-to-read YAML files within nested 
directories to logically group your configurations.
- **Unified Access**: Load all configuration files as a single object for easy access.
- **Values Override**: Dynamically override configuration values using environment variables.
- **Secrets Management**: Encrypt and decrypt sensitive data directly within your configuration files.

### Installation

```shell
pip install pyflexcfg
```

### Configuration

There are several environment variables that could be set in order to adjust PyFlexCfg behaviour:

1. By default, PyFlexCfg looks for configuration files in a directory **config** within the current working directory. 
To specify a different path, define an environment variable with the absolute path to the desired configuration root 
directory:
    ```shell
    PYFLEX_CFG_ROOT_PATH=\path\to\config
    ```

2. In order to use encrypted configuration values, you must set an environment variable with encryption key, which 
will be used for secrets decryption:
    ```shell
    PYFLEX_CFG_KEY=super_secret_key
    ```


### Basic Usage

Assuming the following configuration file structure:
```
    \project  <-- working directory
        ├─ config
            ├─ general.yaml
            ├─ env
                ├─ dev.yaml
                ├─ prd.yaml
   ```
And each YAML file contains a configuration option like this:
```yaml
data: test
```
You can load and use the configurations as follows:

```python
from pyflexcfg import Cfg

print(Cfg.general.data)  # Access data from general.yaml
print(Cfg.env.dev.data)  # Access data from env/dev.yaml
print(Cfg.env.prd.data)  # Access data from env/prd.yaml
```

**Note**: Directory and file names in your configuration structure must be compatible with Python attribute naming 
conventions.

### Overriding values with Environment Variables

You can override values in YAML files using environment variables. To do this, create environment variables that reflect
the configuration values you want to override. This feature is particularly useful in environments like Docker Compose, 
where you can pass environment-specific settings to containers dynamically, enabling seamless configuration management 
across different deployment setups.

For example, if you want to overwrite the value of
```
Cfg.env.dev.data
```
Define an environment variable:
```
CFG__ENV__DEV__DATA=some_value
```
Having that set, call the method 
```python
from pyflexcfg import Cfg

Cfg.update_from_env()
``` 
The value from the environment variable will replace the corresponding value from the YAML file.


### Handling secrets

Any sensitive data present in configuration files should be encrypted!

#### Encrypting a Secret

Use the AESCipher class to encrypt your secrets:
```python
from pyflexcfg import AESCipher

aes = AESCipher('secret-key')
aes.encrypt('some-secret-to-encrypt')
```
This will produce an output like:

```python
b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI'
```
Store the encrypted secret in a YAML file with the **!encr** prefix:

```yaml
my_secret: !encr b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI'
```

#### Decrypting Secrets

When PyFlexCfg loads the configuration and the environment variable **PYFLEX_CFG_KEY** is set with your encryption key, 
it will automatically decrypt values marked with **!encr** prefix and store them in Cfg as a Secret strings, masking 
them in logs and console outputs with ******. 

Use the AESCipher class to manually decrypt your secrets if needed:
```python
from pyflexcfg import AESCipher

aes = AESCipher('secret-key')
aes.decrypt(b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI')
```