
from functools import wraps
from flask import request, jsonify, g
from models.whitelist import is_server_authorized


def require_api_auth(f):
    """
    装饰器：验证 X-API-Key + Server Address
    使用方式：
        @api_bp.route('/auth/verify-game-token', methods=['POST'])
        @require_api_auth
        def verify_game_token():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # 获取请求头
        api_key = request.headers.get('X-API-Key')
        server_addr = request.headers.get('X-Server-Address')

        if not server_addr:
            from flask import current_app
            server_addr = request.remote_addr
            current_app.logger.warning(f"No X-Server-Address header, using remote_addr={server_addr}")

        if not api_key or not server_addr:
            return jsonify({
                "success": False,
                "error": "Missing required headers: X-Server-Address and X-API-Key"
            }), 400

        # 验证
        if not is_server_authorized(server_addr, api_key):
            return jsonify({
                "success": False,
                "error": "Unauthorized server or invalid API key"
            }), 401

        # ✅ 验证通过，继续执行
        g.authenticated_server = server_addr
        return f(*args, **kwargs)

    return decorated