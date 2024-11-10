import base64
import hashlib
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .abstractclasses import ICipher

AES_BLOCK_SIZE = 16


class AESCipher(ICipher):
    def __init__(self, key: str):
        """
        Initializes the AES cipher with a static key provided as a string.
        The string key is hashed to ensure it fits the length in bytes required by AES.

        :param key: encryption key string
        """
        self.key = hashlib.sha256(key.encode('utf-8')).digest()

    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypts a plaintext string using AES CBC mode with PKCS7 padding.

        :param plaintext: plaintext string to encrypt
        :return: encrypted data as bytes IV prepended
        """
        iv = os.urandom(AES_BLOCK_SIZE)
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode('utf-8')) + padder.finalize()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return base64.b64encode(iv + encrypted)

    def decrypt(self, encrypted: bytes | str) -> str:
        """
        Decrypts an encrypted string using AES CBC mode with PKCS7 padding.

        :param encrypted: encrypted data as bytes or string IV prepended
        :return: decrypted plaintext string
        """
        encrypted = base64.b64decode(encrypted)
        iv = encrypted[:AES_BLOCK_SIZE]
        actual_encrypted_data = encrypted[AES_BLOCK_SIZE:]
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(actual_encrypted_data) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext_bytes = unpadder.update(padded_plaintext) + unpadder.finalize()
        return plaintext_bytes.decode('utf-8')
