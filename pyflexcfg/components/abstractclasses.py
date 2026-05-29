from abc import ABC, abstractmethod


class ICipher(ABC):
    @abstractmethod
    def decrypt(self, encrypted: bytes | str) -> str: ...

    @abstractmethod
    def encrypt(self, plaintext: str) -> str: ...
