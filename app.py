# app.py
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from datetime import timedelta
from config import Config
import os
from extensions import csrf


app = Flask(__name__)
def create_app():
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(minutes=60)

    # 注册蓝图
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.github import github_bp
    from routes.api import api_bp

    app.register_blueprint(main_bp, url_prefix='')
    app.register_blueprint(auth_bp, url_prefix='')
    app.register_blueprint(admin_bp, url_prefix='')
    app.register_blueprint(github_bp, url_prefix='')
    app.register_blueprint(api_bp)

    csrf.init_app(app=app)

    return app

'''
@app.route('/debug/routes')
def debug_routes():
    """调试用：列出所有已注册的路由"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,          # 函数名，如 'api.verify_game_token'
            'methods': list(rule.methods),     # 支持的方法，如 ['GET', 'POST']
            'rule': str(rule)                  # URL 规则，如 '/api/v1/auth/verify-game-token'
        })
    return jsonify(routes)
'''
if __name__ == '__main__':
    app = create_app()
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    host = '127.0.0.1' if debug_mode else '0.0.0.0'
    app.run(debug=debug_mode, host=host, port=5000)
