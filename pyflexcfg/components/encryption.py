import base64
import hashlib
import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import padding as _padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .abstractclasses import ICipher

logger = logging.getLogger(__name__)

class _V:
    FAST = b'\x01'
    KDF  = b'\x02'
_GCM_NONCE_SIZE = 12
_KDF_SALT_SIZE = 16
_KDF_ITERATIONS = 480_000
_MIN_KEY_LEN = 32
_CBC_BLOCK_SIZE = 16


class AESCipher(ICipher):
    def __init__(self, key: str) -> None:
        """
        Initialize the cipher with a passphrase.

        The passphrase is SHA-256 hashed into a 32-byte AES key. Keys shorter than
        32 characters are accepted but trigger a WARNING; prefer high-entropy keys.

        Args:
            key: Encryption passphrase.
        """
        if len(key) < _MIN_KEY_LEN:
            logger.warning(
                'PYFLEX_CFG_KEY is shorter than %d characters; use a high-entropy key of at least %d chars.',
                _MIN_KEY_LEN,
                _MIN_KEY_LEN,
            )
        self._passphrase = key.encode('utf-8')
        self._key = hashlib.sha256(self._passphrase).digest()

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt with AES-GCM using SHA-256(passphrase) as the key.

        Ciphertext format (base64): ``\\x01 + nonce[12] + gcm_output``.

        Args:
            plaintext: String to encrypt.

        Returns:
            Base64-encoded ASCII ciphertext string.
        """
        nonce = os.urandom(_GCM_NONCE_SIZE)
        ct = AESGCM(self._key).encrypt(nonce, plaintext.encode('utf-8'), None)
        return base64.b64encode(_V.FAST + nonce + ct).decode('ascii')

    def encrypt_kdf(self, plaintext: str) -> str:
        """
        Encrypt with AES-GCM using PBKDF2-derived key (480k iterations).

        Slower than :meth:`encrypt`; intended for crown-jewel secrets where
        brute-force resistance of the key derivation matters.
        Ciphertext format (base64): ``\\x02 + salt[16] + nonce[12] + gcm_output``.

        Args:
            plaintext: String to encrypt.

        Returns:
            Base64-encoded ASCII ciphertext string.
        """
        salt = os.urandom(_KDF_SALT_SIZE)
        key = self._derive_key(salt)
        nonce = os.urandom(_GCM_NONCE_SIZE)
        ct = AESGCM(key).encrypt(nonce, plaintext.encode('utf-8'), None)
        return base64.b64encode(_V.KDF + salt + nonce + ct).decode('ascii')

    def decrypt(self, ciphertext: bytes | str) -> str:
        """
        Decrypt a ciphertext produced by :meth:`encrypt` or :meth:`encrypt_kdf`.

        Routes automatically by the version byte embedded in the ciphertext.

        Args:
            ciphertext: Base64 ciphertext string or bytes.

        Returns:
            Decrypted plaintext string.

        Raises:
            RuntimeError: Legacy AES-CBC ciphertext detected, or unknown version byte.
            ValueError: Authentication tag mismatch (wrong key or tampered ciphertext).
        """
        raw = base64.b64decode(ciphertext)
        version = raw[:1]

        match version:
            case _V.FAST:
                nonce = raw[1 : 1 + _GCM_NONCE_SIZE]
                ct = raw[1 + _GCM_NONCE_SIZE :]
                key = self._key
            case _V.KDF:
                salt = raw[1 : 1 + _KDF_SALT_SIZE]
                nonce = raw[1 + _KDF_SALT_SIZE : 1 + _KDF_SALT_SIZE + _GCM_NONCE_SIZE]
                ct = raw[1 + _KDF_SALT_SIZE + _GCM_NONCE_SIZE :]
                key = self._derive_key(salt)
            case _:
                if len(raw) >= _CBC_BLOCK_SIZE * 2 and len(raw) % _CBC_BLOCK_SIZE == 0:
                    logger.warning(
                        'Legacy AES-CBC ciphertext decrypted successfully. '
                        'Run `pyflexcfg encrypt` to migrate all !encr values to AES-GCM.'
                    )
                    return self._decrypt_legacy_cbc(raw)

                raise RuntimeError(f'Unknown ciphertext version: {version!r}')

        try:
            return AESGCM(key).decrypt(nonce, ct, None).decode('utf-8')
        except InvalidTag:
            raise ValueError('Decryption failed: wrong key or corrupted ciphertext')

    def _derive_key(self, salt: bytes) -> bytes:
        return PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_KDF_ITERATIONS,
        ).derive(self._passphrase)

    def _decrypt_legacy_cbc(self, raw: bytes) -> str:
        """AES-CBC + PKCS7 decrypt for v2 ciphertexts (no version byte, iv[16] + ct)."""
        iv, ct = raw[:_CBC_BLOCK_SIZE], raw[_CBC_BLOCK_SIZE:]
        decryptor = Cipher(algorithms.AES(self._key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ct) + decryptor.finalize()
        unpadder = _padding.PKCS7(_CBC_BLOCK_SIZE * 8).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')
