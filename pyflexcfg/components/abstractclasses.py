from abc import ABC, abstractmethod


class ICipher(ABC):

    @abstractmethod
    def encrypt(self, plaintext: str) -> bytes: ...

    @abstractmethod
    def decrypt(self, encrypted: bytes | str) -> str: ...
