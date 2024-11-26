# PyFlexCfg

Simple and flexible configuration handler for Python projects.

### Contents
1. [Description](#description)
2. [Features](#features)
3. [Installation](#installation)
4. [Configuration](#configuration)
   - [General](#general)
   - [Logging](#logging)
5. [Basic Usage](#basic-usage)
6. [Overriding values](#overriding-values)
7. [Handling secrets](#handling-secrets)
   - [Encrypting secrets](#encrypting-secrets)
   - [Decrypting secrets](#decrypting-secrets)
8. [Additional constructors](#additional-constructors)
   - [String constructor](#string-constructor)
   - [Paths constructors](#paths-constructors)

### Description

**PyFlexCfg** allows you to store your project's configuration in YAML files and seamlessly load them as a unified 
object when imported into your Python code.

The handler is using **PyYAML** library for handling YAML files due to its lower dependencies footprint and loading 
speed, therefore YAML files of version 1.2 might not be loaded properly.

### Features:

- **YAML config**: Organize your project's settings using easy-to-read YAML files within nested 
directories to logically group your configurations.
- **Unified Access**: Load all configuration files as a single object for easy access.
- **Values Override**: Dynamically override configuration values using environment variables.
- **Secrets Management**: Encrypt and decrypt sensitive data directly within your configuration files
- **Additional constructors**: several custom YAML constructors to expand functionality of the configuration.

### Installation

```shell
pip install pyflexcfg
```

### Configuration

#### General

There are several options that could be set as an environment variable in order to adjust PyFlexCfg behaviour:

1. By default, **PyFlexCfg** looks for configuration files in a directory **config** within the current working directory. 
To specify a different path, define an environment variable with the absolute path to the desired configuration root 
directory:
    ```shell
    PYFLEX_CFG_ROOT_PATH=/path/to/config
    ```

2. In order to use encrypted configuration values, you must set an environment variable with encryption key, which 
will be used for secrets decryption:
    ```shell
    PYFLEX_CFG_KEY=super_secret_key
    ```

#### Logging

In case you want to enable logging for the handler you can get the appropriate logger by executing:
```python
import logging

cfg_logger = logging.getLogger('pyflexcfg')

```
After that you can configure logging options, add logger handlers and so on the way you prefer.

### Basic Usage

Assuming the following configuration file structure:
```
 \project               <-- working directory
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

**Note**: Directories, file names and value names in your configuration structure **must be compatible** with Python 
attribute naming rules.

### Overriding values

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

Any sensitive data present in configuration files should be kept as encrypted!

**PyFlexCfg** allows you to encrypt your sensitive date with AES encryption prior to placing it in config files and 
auto-decrypt it upon configuration loading if you have an encryption key set in environment variable. 

#### Encrypting secrets

Use the AESCipher class to encrypt your secrets before putting them in config files:
```python
from pyflexcfg import AESCipher

aes = AESCipher('secret-key')
aes.encrypt('some-secret-to-encrypt')
```
This will produce an output like:

```python
b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI'
```
Store the encrypted secret as bytes or string in a YAML file with the **!encr** prefix:

```yaml
my_secret: !encr b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI'  # as bytes
```
```yaml
my_secret: !encr A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI  # as string
```

#### Decrypting secrets

When **PyFlexCfg** loads the configuration and the environment variable **PYFLEX_CFG_KEY** is set with your encryption key, 
it will automatically decrypt values marked with **!encr** prefix and store them in Cfg as a Secret strings, masking 
them in logs and console outputs with ******. 

Use the AESCipher class to manually decrypt your secrets if needed:
```python
from pyflexcfg import AESCipher

aes = AESCipher('secret-key')
aes.decrypt(b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI')
```

### Additional constructors

Several custom constructors are available for use in your configuration files to expand its functionality:

#### String constructor
   
Implemented with the **!string** prefix and can be used for composing strings, URLs and so on.

String construction example:

Assume having a file ./config/data.yaml with content
```yaml
string_var: !string ['This', ' is', ' a', ' test', ' string']
```
```python
from pyflexcfg import Cfg
print(Cfg.data.string_var)

>> 'This is a test string'
```

URL construction example:

Assume having a file ./config/data.yaml with content
```yaml
base_url: &base https://test.com
slug: &slug /test/
full_url: !string [*base, *slug, index.html]
```
```python
from pyflexcfg import Cfg
print(Cfg.data.full_url)

>> 'https://test.com/test/index.html'
```

#### Paths constructors

There are two paths constructors presented by prefixes **!path_win** and **!path_posix**. 
Their purpose is to compose and return **PureWindowsPath** and **PurePosixPath** pathlib instances.

Assume having a file ./config/data.yaml with content
```yaml
path_win: !path_win ['C:\', Test, files, test_file.txt]
path_posix: !path_posix [/var, log, test.log]
```
```python
from pyflexcfg import Cfg

print(Cfg.data.path_win)
>> PureWindowsPath('C:/Test/files/test_file.txt')

print(Cfg.data.path_posix)
>> PurePosixPath('/var/log/test.log')
```

In addition, there is one more path constructor presented with **!home_dir** prefix. Its purpose to be used as a base 
for paths originating from User's home directory (OS independent). It returns a **PurePath** pathlib instance.

Assume having a file ./config/data.yaml with content and logged in as **user**
```yaml
path: !home_dir [app, logs]
```

For Unix OS:
```python
from pyflexcfg import Cfg

print(Cfg.data.path)
>> PurePath('/home/user/app/log/')
```

For Windows OS:
```python
from pyflexcfg import Cfg

print(Cfg.data.path)
>> PurePath('C:/Users/user/app/log/')
```