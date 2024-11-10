# PyFlexCfg

Flexible configuration handler for Python projects.

### Description

The handler (a.k.a. Cfg) allows to store project's configuration in YAML files and load them at once when imported.

### Installation

```shell
pip install pyflexcfg
```

### Configuration

In order to use encryption\decryption for configuration secrets, make sure to
set an environment variable **PYFLEX_CFG_KEY** with some encryption key, which will be
used for secrets encryption\decryption.

By default, Cfg searches for configuration files in the **config** directory
within current working dir. In order to specify a different path, crate a nenv variable
**PYFLEX_CFG_ROOT_PATH** with the absolute path to the configuration root.

### Basic Usage

Assuming you have such configuration files structure:
```
    \project
        ├─ config
            ├─ general.yaml
            ├─ env
                ├─ dev.yaml
                ├─ prd.yaml
   ```
And each of the yaml files contains a configuration option **data: test**

Just import the Cfg and you can use your configuration at once:

```python
from pyflexcfg import Cfg

print(Cfg.general.data)
print(Cfg.env.dev.data)
print(Cfg.env.prd.data)
```

Make sure the names of directories within your configuration are Python object's attribute name compatible.


### Override by environment variables

There is an option to override values in YAML files with values from environment variables.
In order to do so, you have to create env variables which reflect the name of config value to be overwritten.
For example, if you want to overwrite value for
```
Cfg.env.dev.data
```
you have to create env variable like this
```
CFG__ENV__DEV__DATA
```
Having that, you can call 
```python
Cfg.update_from_env()
``` 
and the value from the YAML file will be overwritten by the value from env variable.


### Handling secrets

Any sensitive data to be stored within your configuration files should be encrypted!

Encrypt your secret:
```python
from pyflexcfg import AESCipher

aes = AESCipher('secret-key')
aes.encrypt('some-secret-to-encrypt')
```
You will get output like

```python
b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI'
```
and it can be stored in yaml file with **!encr** prefix:

```yaml
my_secret: !encr b'A1u6BIE2xGtYTSoFRE83H0VHsAW3nrv4WB+T/FEAj1fsh8HIId9r/Rskl0bnDHTI'
```

The next time Cfg will be loading this configuration file it will automatically decrypt
this value, but do not forget to set up env variable **PYFLEX_CFG_KEY** with your 'secret-key',
otherwise Cfg won't be able to decrypt the data.