import base64
import os
import platform
import logging

logger = logging.getLogger("IRD_Security")

# Attempt DPAPI via win32crypt
HAS_DPAPI = False
try:
    if platform.system() == "Windows":
        import win32crypt
        HAS_DPAPI = True
except ImportError:
    HAS_DPAPI = False

# Fallback encryption using Cryptography Fernet if DPAPI unavailable
from cryptography.fernet import Fernet

def _get_fallback_key() -> bytes:
    """Generates a stable machine-bound key for fallback encryption."""
    user_system_str = f"{os.getenv('COMPUTERNAME', 'LOCAL')}-{os.getenv('USERNAME', 'USER')}-IRD-SYNC-SALT"
    key_bytes = user_system_str.encode('utf-8')
    padded = (key_bytes * (32 // len(key_bytes) + 1))[:32]
    return base64.urlsafe_b64encode(padded)


def encrypt_password(plain_password: str) -> str:
    """
    Encrypts password using Windows DPAPI (CryptProtectData).
    Falls back to Fernet if DPAPI is not available.
    Never returns plaintext.
    """
    if not plain_password:
        return ""

    try:
        if HAS_DPAPI:
            # DPAPI protects data using current Windows user context
            data_bytes = plain_password.encode('utf-8')
            encrypted_bytes = win32crypt.CryptProtectData(data_bytes, "IRD_Credential", None, None, None, 0)
            return "dpapi:" + base64.b64encode(encrypted_bytes).decode('ascii')
        else:
            fernet = Fernet(_get_fallback_key())
            encrypted = fernet.encrypt(plain_password.encode('utf-8'))
            return "fernet:" + encrypted.decode('ascii')
    except Exception as e:
        logger.error(f"Error encrypting password: {e}")
        # Secondary fallback
        fernet = Fernet(_get_fallback_key())
        encrypted = fernet.encrypt(plain_password.encode('utf-8'))
        return "fernet:" + encrypted.decode('ascii')


def decrypt_password(encrypted_str: str) -> str:
    """
    Decrypts password encrypted by encrypt_password.
    Returns plaintext string. Handles DPAPI or Fernet prefixes.
    """
    if not encrypted_str:
        return ""

    try:
        if encrypted_str.startswith("dpapi:"):
            if HAS_DPAPI:
                raw_b64 = encrypted_str[6:]
                encrypted_bytes = base64.b64decode(raw_b64)
                _, decrypted_bytes = win32crypt.CryptUnprotectData(encrypted_bytes, None, None, None, 0)
                return decrypted_bytes.decode('utf-8')
            else:
                logger.error("Cannot decrypt DPAPI credential on non-Windows/missing win32crypt environment.")
                return ""
        elif encrypted_str.startswith("fernet:"):
            raw_token = encrypted_str[7:].encode('ascii')
            fernet = Fernet(_get_fallback_key())
            return fernet.decrypt(raw_token).decode('utf-8')
        else:
            # Unencrypted string fallback for migration safety
            return encrypted_str
    except Exception as e:
        logger.error(f"Failed to decrypt credential: {e}")
        return ""


def mask_password(password: str) -> str:
    """Returns a masked representation of the password for UI rendering."""
    if not password:
        return ""
    return "●" * min(len(password), 12)
