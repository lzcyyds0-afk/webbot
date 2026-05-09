from cryptography.fernet import Fernet
from app.core.config import settings


def _get_fernet() -> Fernet:
    return Fernet(settings.get_fernet_key().encode())


def encrypt_value(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()
