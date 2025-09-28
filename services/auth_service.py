# auth_services.py
from models.user import (
    get_user_by_username,
    update_last_login,
    get_user_totp_info,
    update_totp_last_used,
    get_user_by_id
)
from models.reputation import update_reputation
from utils.security import check_password
from utils.security import generate_secure_token
from utils.validators import validate_user_id
import pyotp
import utils
from models.database import get_db_cursor
import logging


# ======================
# 用户基本认证
# ======================

def authenticate_user(username, password):
    """用户认证：验证用户名和密码"""
    user = get_user_by_username(username)
    if user and check_password(password, user['password_hash']):
        return user
    return None


def login_user(user_id, session, username):
    """处理用户登录，写入 session"""
    validate_user_id(user_id)
    update_last_login(user_id)

    session['user_id'] = user_id
    session['username'] = username
    session.permanent = True


# ======================
# 2FA 验证流程
# ======================

def process_2fa_verification(user_id, token, session):
    """处理 TOTP 2FA 验证"""
    totp_info = get_user_totp_info(user_id)
    if not totp_info:
        return False

    try:
        secret = utils.decrypt_data(totp_info['totp_secret_encrypted'], totp_info['backup_codes_salt'])
        totp = pyotp.TOTP(secret)

        if totp.verify(token):
            user = get_user_by_id(user_id)
            session['user_id'] = user_id
            session['username'] = user['username']
            session.pop('pending_2fa_user_id', None)
            session.pop('2fa_stage', None)

            # 更新最后使用时间
            update_totp_last_used(user_id)

            # 检查是否是首次 2FA 成功
            check_first_2fa_verification(user_id)

            return True
    except Exception as e:
        logging.error(f"TOTP verification failed for user_id={user_id}: {e}")

    return False


def process_backup_code_verification(user_id, token, session):
    """处理备份码验证"""
    totp_info = get_user_totp_info(user_id)
    if not totp_info or not totp_info['backup_codes_encrypted']:
        return False

    try:
        decrypted = utils.decrypt_data(totp_info['backup_codes_encrypted'], totp_info['backup_codes_salt'])
        codes = set(decrypted.split(","))
        if token in codes:
            codes.remove(token)
            new_encrypted, _ = utils.encrypt_data(",".join(codes), totp_info['backup_codes_salt'])
            from models.user import update_backup_codes
            update_backup_codes(user_id, new_encrypted)

            user = get_user_by_id(user_id)
            session['user_id'] = user_id
            session['username'] = user['username']
            session.pop('pending_2fa_user_id', None)
            session.pop('2fa_stage', None)

            update_totp_last_used(user_id)
            check_first_2fa_verification(user_id)

            return True
    except Exception as e:
        logging.error(f"Backup code verification failed for user_id={user_id}: {e}")

    return False


def check_first_2fa_verification(user_id):
    """检查是否为首次成功完成 2FA（包括 TOTP 或备份码）"""
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) AS usage_count 
            FROM taUsersReputationLogs 
            WHERE user_id = %s AND change_type = 'first_2fa_verification'
        """, (user_id,))
        log_entry = cursor.fetchone()

        if log_entry and log_entry['usage_count'] == 0:
            update_reputation(
                user_id=user_id,
                change_type='first_2fa_verification',
                amount=10,
                description="首次成功完成2FA验证"
            )


# ======================
# Game Token API 服务
# ======================

def create_or_update_game_token(user_id):
    from utils.security import generate_secure_token
    import utils
    from models.database import get_db_cursor
    from flask import current_app

    token_plaintext = generate_secure_token()
    encrypted_token, salt = utils.encrypt_data(token_plaintext, None)  # 返回 (bytes, str)

    # 确保 salt 是 32 字符字符串
    if len(salt) != 32:
        salt = salt[:32].ljust(32, '0')  # 截取或补零

    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO taUserGame (user_id, game_token, salt)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET game_token = EXCLUDED.game_token, salt = EXCLUDED.salt, updated_at = NOW()
                RETURNING id
            """, (user_id, encrypted_token, salt))

            result = cursor.fetchone()
            if not result:
                raise Exception("Failed to insert or update game token")

        current_app.logger.info(f"Game token generated for user_id={user_id}")
        return token_plaintext

    except Exception as e:
        current_app.logger.error(f"Error creating game token: {e}")
        raise


def authenticate_with_game_token(token):
    """
    使用 game token 认证用户
    解密所有 token 并比对（安全做法）
    返回用户信息或 None
    """
    if not token or len(token) < 32:
        return None

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT user_id, game_token, backup_codes_salt AS salt
            FROM taUserGame
            WHERE created_at > NOW() - INTERVAL '90 days'  -- 可选过期策略
        """)
        records = cursor.fetchall()

    matched_user_id = None
    for record in records:
        try:
            decrypted = utils.decrypt_data(record['game_token'], record['salt'])
            if decrypted == token:
                matched_user_id = record['user_id']
                break
        except Exception as e:
            logging.warning(f"Failed to decrypt game token for user_id={record['user_id']}: {e}")

    if not matched_user_id:
        return None

    user = get_user_by_id(matched_user_id)
    if not user:
        return None

    # 更新最后使用时间
    _update_game_token_last_used(matched_user_id)
    update_last_login(matched_user_id)

    logging.info(f"Authenticated via game token: {matched_user_id}")
    return user


def _update_game_token_last_used(user_id):
    """更新 token 的 last_used_at 时间"""
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE taUserGame
            SET last_used_at = NOW()
            WHERE user_id = %s
        """, (user_id,))


def refresh_game_token(user_id):
    """刷新用户的 game token（重新生成）"""
    return create_or_update_game_token(user_id)


def revoke_game_token(user_id):
    """撤销用户的 game token"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM taUserGame WHERE user_id = %s", (user_id,))
    logging.info(f"Game token revoked for user_id: {user_id}")


def get_game_token_info(user_id):
    """获取 token 元信息（用于前端显示）"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT created_at, updated_at, last_used_at
            FROM taUserGame
            WHERE user_id = %s
        """, (user_id,))
        return cursor.fetchone()
