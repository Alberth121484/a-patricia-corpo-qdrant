"""
Security utilities: JWT tokens and encryption
"""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
import json

from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_encryption_key() -> bytes:
    """Derive a valid Fernet key from the encryption key setting"""
    key = settings.ENCRYPTION_KEY.encode()
    # Use PBKDF2 to derive a valid 32-byte key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"patricia-salt-v1",  # Static salt for consistency
        iterations=100000,
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(key))
    return derived_key


# Encryption cipher
_fernet = None


def get_fernet() -> Fernet:
    """Get or create Fernet cipher"""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_encryption_key())
    return _fernet


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def encrypt_data(data: dict) -> str:
    """Encrypt data dictionary to string"""
    json_data = json.dumps(data)
    encrypted = get_fernet().encrypt(json_data.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_data(encrypted_str: str) -> dict:
    """Decrypt string to data dictionary"""
    encrypted = base64.urlsafe_b64decode(encrypted_str.encode())
    decrypted = get_fernet().decrypt(encrypted)
    return json.loads(decrypted.decode())


def generate_file_id() -> str:
    """Generate a unique file ID"""
    return secrets.token_urlsafe(16)
