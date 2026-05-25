import base64
import hashlib
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .abstractclasses import ICipher

AES_BLOCK_SIZE = 16


class AESCipher(ICipher):
    def __init__(self, key: str) -> None:
        """
        Initialize the AES cipher with a static key.

        The string key is SHA-256 hashed to produce the 32-byte AES key.

        Args:
            key: Encryption key as a string.
        """
        self.key = hashlib.sha256(key.encode('utf-8')).digest()

    def decrypt(self, encrypted: bytes | str) -> str:
        """
        Decrypt an AES-CBC + PKCS7 ciphertext produced by :meth:`encrypt`.

        Args:
            encrypted: Base64 ciphertext with IV prepended, as bytes or str.

        Returns:
            Decrypted plaintext string.
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

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string using AES-CBC with PKCS7 padding.

        Args:
            plaintext: String to encrypt.

        Returns:
            Base64-encoded ASCII string with the IV prepended to the ciphertext.
        """
        iv = os.urandom(AES_BLOCK_SIZE)
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode('utf-8')) + padder.finalize()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()

        return base64.b64encode(iv + encrypted).decode('ascii')
