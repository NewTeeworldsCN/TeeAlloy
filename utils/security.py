# utils/security.py
import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import pyotp
import qrcode
import io
import base64
import os
import secrets
import string

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def get_fernet():
    """获取全局 Fernet 实例（需确保 FERNET_KEY 已设置）"""
    key = os.environ.get("FERNET_KEY")
    if not key:
        raise RuntimeError("FERNET_KEY 环境变量未设置")
    return Fernet(key.encode())

def derive_key_from_password(password: str, salt: str) -> bytes:
    """使用 PBKDF2 从密码和 salt 派生密钥"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=bytes.fromhex(salt),
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key

def encrypt_data(data: str, key_salt: str = None) -> tuple[bytes, str]:
    """加密字符串数据，返回 (ciphertext_bytes, salt_used)"""
    salt = key_salt or os.urandom(16).hex()
    key = derive_key_from_password(os.environ.get("FERNET_KEY", ""), salt)
    f = Fernet(key)
    encrypted = f.encrypt(data.encode('utf-8'))
    return (encrypted, salt)

def decrypt_data(data: bytes, salt: str) -> str:
    """用 salt 解密数据"""
    if isinstance(data, memoryview):
        data = data.tobytes()
    key = derive_key_from_password(os.environ.get("FERNET_KEY", ""), salt)
    f = Fernet(key)
    decrypted = f.decrypt(data)
    return decrypted.decode('utf-8')

def generate_totp_secret() -> str:
    """生成 TOTP 密钥（base32 编码）"""
    return pyotp.random_base32()

def get_totp_uri(username: str, secret: str) -> str:
    """生成 TOTP URI（用于生成二维码）"""
    issuer = "TeeAlloy"
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=issuer
    )

def make_qr_code_image(uri: str) -> str:
    """生成二维码图片（Base64 编码的 PNG）"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

def generate_secure_token(length=64):
    """生成安全的随机 token"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))