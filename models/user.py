from models.database import get_db_cursor
from utils.security import hash_password, check_password
from utils.validators import validate_user_id
import uuid
import re

def create_user(username, nickname, password):
    """创建新用户"""
    # 检查用户名格式
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_]{2,31}$', username) or len(username) < 6:
        raise ValueError('用户名必须为6-32个字符，只能包含字母、数字和下划线，且必须以字母或数字开头')
    
    if not (1 <= len(nickname) <= 16):
        raise ValueError('昵称应当在1-16个字及之间')
    if len(password) < 6:
        raise ValueError('密码必须至少为6个字符')

    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM taUsers WHERE username = %s", (username,))
        if cursor.fetchone():
            raise ValueError('用户名已存在')

        password_hash = hash_password(password)
        user_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO taUsers (id, username, nickname, password_hash)
            VALUES (%s, %s, %s, %s)
        """, (user_id, username, nickname, password_hash))
        
        return user_id

def get_user_by_username(username):
    """根据用户名获取用户信息"""
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id, username, password_hash, is_2fa_enabled, is_admin FROM taUsers WHERE username = %s",
            (username,)
        )
        return cursor.fetchone()

def update_last_login(user_id):
    """更新用户最后登录时间"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute(
            "UPDATE taUsers SET last_login = NOW() WHERE id = %s",
            (user_id,)
        )

def get_user_by_id(user_id):
    """根据ID获取用户信息"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM taUsers WHERE id = %s", (user_id,))
        return cursor.fetchone()

def get_user_github_info(user_id):
    """获取用户GitHub信息"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("SELECT github_login, avatar_url FROM taUserGitHub WHERE user_id = %s", (user_id,))
        return cursor.fetchone()

def get_user_totp_info(user_id):
    """获取用户TOTP信息"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT t.totp_secret_encrypted, t.backup_codes_salt, t.backup_codes_encrypted
            FROM taUserTOTP t
            WHERE t.user_id = %s
        """, (user_id,))
        return cursor.fetchone()

def get_user_game_token_info(user_id):
    """获取用户的 game token 元数据（不含明文）"""
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT created_at, updated_at, last_used_at
            FROM taUserGame
            WHERE user_id = %s
        """, (user_id,))
        return cursor.fetchone()

def update_user_totp(user_id, encrypted_secret, encrypted_backup, salt):
    """更新用户TOTP信息"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO taUserTOTP (user_id, totp_secret_encrypted, backup_codes_encrypted, backup_codes_salt)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                totp_secret_encrypted = EXCLUDED.totp_secret_encrypted,
                backup_codes_encrypted = EXCLUDED.backup_codes_encrypted,
                backup_codes_salt = EXCLUDED.backup_codes_salt,
                updated_at = NOW()
        """, (user_id, encrypted_secret, encrypted_backup, salt))

        cursor.execute("UPDATE taUsers SET is_2fa_enabled = TRUE WHERE id = %s", (user_id,))

def delete_user_totp(user_id):
    """删除用户TOTP信息"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM taUserTOTP WHERE user_id = %s", (user_id,))
        cursor.execute("UPDATE taUsers SET is_2fa_enabled = FALSE WHERE id = %s", (user_id,))

def update_totp_last_used(user_id):
    """更新TOTP最后使用时间"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("UPDATE taUserTOTP SET last_used_at = NOW() WHERE user_id = %s", (user_id,))

def update_backup_codes(user_id, new_encrypted_codes):
    """更新备份码"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute(
            "UPDATE taUserTOTP SET backup_codes_encrypted = %s WHERE user_id = %s",
            (new_encrypted_codes, user_id)
        )

def update_user_nickname(user_id, new_nickname):
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute(
            "UPDATE taUsers SET nickname = %s WHERE id = %s",
            (new_nickname, user_id)
        )