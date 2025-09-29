# routes/api.py
from flask import Blueprint, request, jsonify, g
from functools import lru_cache
import logging
from datetime import datetime, timezone
from flask_wtf.csrf import CSRF
from extensions import csrf

from models.database import get_db_cursor
from models.user import get_user_by_id
import utils
from utils.decorators import require_api_auth

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')
logger = logging.getLogger(__name__)


def _decrypt_and_match(encrypted_token_bytes: bytes, salt: str, target_token: str) -> bool:
    """
    尝试用 salt 解密 encrypted_token_bytes，并与 target_token 比较。
    安全、防崩溃、防时序攻击。
    """
    if isinstance(encrypted_token_bytes, memoryview):
        encrypted_token_bytes = encrypted_token_bytes.tobytes()
    if not isinstance(encrypted_token_bytes, bytes) or len(encrypted_token_bytes) == 0:
        logger.warning("Invalid encrypted token: not bytes or empty")
        return False
    if not isinstance(salt, str) or len(salt) != 32:  # 假设 salt 固定为 32 字符
        logger.warning("Invalid salt length or type")
        return False
    if not isinstance(target_token, str) or len(target_token.strip()) == 0:
        logger.warning("Invalid target token")
        return False

    target_token = target_token.strip()

    try:
        decrypted: str = utils.decrypt_data(encrypted_token_bytes, salt)
        if not isinstance(decrypted, str):
            logger.warning("Invalid decrypted")
            return False
        import hmac
        return hmac.compare_digest(decrypted.strip(), target_token)
    except Exception as e:
        logger.warning(f"Decryption failed: {e}")
        return False


@api_bp.route('/auth/verify-game-token', methods=['POST'])
@require_api_auth
@csrf.exempt
def verify_game_token():
    data = request.get_json()
    token = data.get("game_token")

    if not token or not isinstance(token, str) or len(token.strip()) == 0:
        return jsonify({"success": False, "error": "Missing or invalid game_token"}), 400
    token = token.strip()

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT ug.user_id, ug.game_token, ug.salt
            FROM taUserGame ug
            WHERE ug.created_at > NOW() - INTERVAL '90 days'
              AND ug.salt IS NOT NULL
        """)
        records = cursor.fetchall()

    matched_user_id = None
    for record in records:
        if _decrypt_and_match(record['game_token'], record['salt'], token):
            matched_user_id = record['user_id']
            break

    if not matched_user_id:
        logger.warning(f"Token verification failed for server={g.authenticated_server}")
        return jsonify({
            "success": False,
            "error": "Invalid or expired game_token"
        }), 401

    user = get_user_by_id(matched_user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT new_score
            FROM taUsersReputationLogs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (matched_user_id,))
        row = cursor.fetchone()
        reputation = row['new_score'] if row else 0

    with get_db_cursor() as cursor:
        cursor.execute("UPDATE taUserGame SET last_used_at = NOW() WHERE user_id = %s", (matched_user_id,))

    logger.info(f"Game token verified | user_id={matched_user_id} | server={g.authenticated_server}")

    return jsonify({
        "success": True,
        "user": {
            "user_id": user['id'],
            "username": user['username'],
            "nickname": user.get('nickname'),
            "reputation": reputation,
            "created_at": user['created_at']
        }
    })



@api_bp.route('/healthz', methods=['GET'])
@csrf.exempt
def health_check():
    """
    健康检查接口，用于监控、负载均衡、CI/CD 部署验证。
    检查：服务是否运行、数据库是否可连接。
    """
    try:
        # 1. 简单数据库连接测试
        with get_db_cursor() as cursor:
            cursor.execute("SELECT 1 AS db_check")
            cursor.fetchone()

        logger.info("Health check passed")
        return jsonify({
            "status": "ok",
            "service": "teealloy-auth-api",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }), 200

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "error",
            "message": "Service is unhealthy",
            "error": str(e)
        }), 500