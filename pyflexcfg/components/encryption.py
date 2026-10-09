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


_CBC_BLOCK_SIZE = 16
_GCM_NONCE_SIZE = 12
_GCM_TAG_SIZE = 16
_KDF_ITERATIONS = 480_000
_KDF_SALT_SIZE = 16
_MAGIC = b'PFLX'
_MIN_KEY_LEN = 32


class _V:
    FAST = _MAGIC + b'\x01'
    KDF = _MAGIC + b'\x02'


_HEADER_SIZE = len(_V.FAST)
# Shortest valid ciphertext per format: what encrypting an empty string produces.
_MIN_SIZES = {
    _V.FAST: _HEADER_SIZE + _GCM_NONCE_SIZE + _GCM_TAG_SIZE,
    _V.KDF: _HEADER_SIZE + _KDF_SALT_SIZE + _GCM_NONCE_SIZE + _GCM_TAG_SIZE,
}


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

    def decrypt(self, ciphertext: bytes | str) -> str:
        """
        Decrypt a ciphertext produced by :meth:`encrypt` or :meth:`encrypt_kdf`.

        Routes by the header (``PFLX`` marker + version byte). Input without the
        marker is treated as a v2 AES-CBC ciphertext and decrypted with a WARNING.

        Args:
            ciphertext: Base64 ciphertext string or bytes.

        Returns:
            Decrypted plaintext string.

        Raises:
            RuntimeError: Unknown version byte, or input in neither format.
            ValueError: Wrong key or corrupted ciphertext.
        """
        raw = base64.b64decode(ciphertext)
        header, body = raw[:_HEADER_SIZE], raw[_HEADER_SIZE:]

        if len(raw) < _MIN_SIZES.get(header, 0):
            raise ValueError('Decryption failed: ciphertext is truncated')

        match header:
            case _V.FAST:
                nonce = body[:_GCM_NONCE_SIZE]
                ct = body[_GCM_NONCE_SIZE:]
                key = self._key
            case _V.KDF:
                salt = body[:_KDF_SALT_SIZE]
                nonce = body[_KDF_SALT_SIZE : _KDF_SALT_SIZE + _GCM_NONCE_SIZE]
                ct = body[_KDF_SALT_SIZE + _GCM_NONCE_SIZE :]
                key = self._derive_key(salt)
            case _ if header.startswith(_MAGIC):
                raise RuntimeError(f'Unknown ciphertext version: {header[-1:]!r}')
            case _ if _has_cbc_shape(raw):
                plaintext = self.decrypt_legacy(ciphertext)
                logger.warning(
                    'Legacy AES-CBC ciphertext decrypted successfully. '
                    'Run `pyflexcfg encrypt` to migrate all !encr values to AES-GCM.'
                )
                return plaintext
            case _:
                raise RuntimeError('Unrecognized ciphertext format')

        try:
            return AESGCM(key).decrypt(nonce, ct, None).decode('utf-8')
        except InvalidTag:
            raise ValueError('Decryption failed: wrong key or corrupted ciphertext')

    def decrypt_legacy(self, ciphertext: bytes | str) -> str:
        """
        Decrypt a v2 AES-CBC ciphertext (base64 of ``iv[16] + ct``, no header).

        Args:
            ciphertext: Base64 ciphertext string or bytes.

        Returns:
            Decrypted plaintext string.

        Raises:
            ValueError: Not CBC-shaped, wrong key, or corrupted ciphertext.
        """
        raw = base64.b64decode(ciphertext)

        if not _has_cbc_shape(raw):
            raise ValueError('Not a legacy AES-CBC ciphertext')

        iv, ct = raw[:_CBC_BLOCK_SIZE], raw[_CBC_BLOCK_SIZE:]
        decryptor = Cipher(algorithms.AES(self._key), modes.CBC(iv)).decryptor()
        unpadder = _padding.PKCS7(_CBC_BLOCK_SIZE * 8).unpadder()

        try:
            padded = decryptor.update(ct) + decryptor.finalize()
            return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')
        except ValueError:
            raise ValueError('Decryption failed: wrong key or corrupted ciphertext') from None

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt with AES-GCM using SHA-256(passphrase) as the key.

        Ciphertext format (base64): ``PFLX + \\x01 + nonce[12] + gcm_output``.

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
        Ciphertext format (base64): ``PFLX + \\x02 + salt[16] + nonce[12] + gcm_output``.

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

    @staticmethod
    def has_marker(value: bytes | str) -> bool:
        """Tell whether `value` carries the ``PFLX`` marker, even if truncated or of an unknown version."""
        return _decode_strict(value).startswith(_MAGIC)

    @staticmethod
    def is_encrypted(value: bytes | str) -> bool:
        """Tell whether `value` is a complete ciphertext in the current AES-GCM format."""
        return _is_complete(_decode_strict(value))

    @staticmethod
    def is_kdf(value: bytes | str) -> bool:
        """Tell whether `value` is a complete current-format ciphertext made by :meth:`encrypt_kdf`."""
        raw = _decode_strict(value)
        return raw.startswith(_V.KDF) and _is_complete(raw)

    @staticmethod
    def is_legacy(value: bytes | str) -> bool:
        """Tell whether `value` has the shape of a v2 AES-CBC ciphertext."""
        raw = _decode_strict(value)
        return not raw.startswith(_MAGIC) and _has_cbc_shape(raw)

    def _derive_key(self, salt: bytes) -> bytes:
        return PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_KDF_ITERATIONS,
        ).derive(self._passphrase)


def _decode_strict(value: bytes | str) -> bytes:
    """Base64-decode `value`, returning empty bytes when it is not valid base64."""
    try:
        return base64.b64decode(value, validate=True)
    except ValueError:
        return b''


def _is_complete(raw: bytes) -> bool:
    """Tell whether `raw` has a known header and at least that format's salt, nonce and GCM tag."""
    min_size = _MIN_SIZES.get(raw[:_HEADER_SIZE])
    return min_size is not None and len(raw) >= min_size


def _has_cbc_shape(raw: bytes) -> bool:
    return len(raw) >= _CBC_BLOCK_SIZE * 2 and len(raw) % _CBC_BLOCK_SIZE == 0
