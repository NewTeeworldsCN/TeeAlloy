# routes/main.py
from flask import Blueprint, render_template, session, flash, redirect, url_for, jsonify, request
from utils.validators import validate_user_id
from models.user import get_user_by_id, get_user_github_info, get_user_game_token_info
from models.reputation import get_user_reputation
from services.auth_service import create_or_update_game_token, revoke_game_token
from services.reputation_service import handle_user_endorsement
import logging

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


@main_bp.route('/')
def index():
    if session.get('user_id'):
        user_id = session.get('user_id')
        if not validate_user_id(user_id):
            session.clear()
            return render_template('index.html', user=None)
        return render_template('index.html', user=True)
    else:
        return render_template('index.html', user=None)


@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    if not validate_user_id(user_id):
        session.clear()
        flash('会话异常，请重新登录')
        return redirect(url_for('auth.login'))

    try:
        user = get_user_by_id(user_id)
        if not user:
            session.clear()
            flash('未找到用户，请重新登录')
            return redirect(url_for('auth.login'))
        
        reputation = get_user_reputation(user_id)
        reputation_score = reputation['score'] if reputation else 0
        
        github_info = get_user_github_info(user_id)
        totp_enabled = bool(user['is_2fa_enabled'])

        return render_template('dashboard.html', 
                             user=user, 
                             totp_enabled=totp_enabled, 
                             reputation=reputation_score, 
                             github=github_info)

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Dashboard error: {e}")
        flash('加载仪表盘时发生错误')
        return redirect(url_for('main.index'))


@main_bp.route('/tokens')
def tokens():
    """用户管理 game_token 的页面"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    if not validate_user_id(user_id):
        session.clear()
        flash('会话异常，请重新登录')
        return redirect(url_for('auth.login'))

    try:
        user = get_user_by_id(user_id)
        if not user:
            session.clear()
            flash('用户不存在')
            return redirect(url_for('auth.login'))

        # 获取 token 信息
        token_info = get_user_game_token_info(user_id)  # 我们稍后定义这个函数

        has_token = token_info is not None
        token_created_at = token_info['created_at'] if has_token else None
        token_updated_at = token_info['updated_at'] if has_token else None
        token_last_used = token_info['last_used_at'] if has_token else None

        return render_template('tokens.html',
                             user=user,
                             has_token=has_token,
                             created_at=token_created_at,
                             updated_at=token_updated_at,
                             last_used=token_last_used)

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Tokens page error: {e}")
        flash('加载令牌页面失败')
        return redirect(url_for('main.dashboard'))


@main_bp.route('/tokens/generate', methods=['POST'])
def generate_token():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    if not validate_user_id(user_id):
        session.clear()
        flash('会话异常')
        return redirect(url_for('auth.login'))

    try:
        token = create_or_update_game_token(user_id)
        session['new_generated_token'] = token  # ⚠️ 仅一次显示
        logger.info(f"New game token generated for user_id={user_id}")
        return redirect(url_for('main.show_new_token'))
    except Exception as e:
        logger.error(f"Failed to generate token: {e}")
        flash("生成失败")
        return redirect(url_for('main.tokens'))

@main_bp.route('/tokens/show-new')
def show_new_token():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    token = session.pop('new_generated_token', None)
    if not token:
        flash("无新生成的 token")
        return redirect(url_for('main.tokens'))

    return render_template('show_new_token.html', token=token)


@main_bp.route('/tokens/refresh', methods=['POST'])
def refresh_token():
    """刷新 token（重新生成）"""
    if 'user_id' not in session:
        return jsonify({"error": "未登录"}), 401

    user_id = session['user_id']
    if not validate_user_id(user_id):
        session.clear()
        return jsonify({"error": "会话异常"}), 401

    try:
        old_info = get_user_game_token_info(user_id)
        if not old_info:
            flash("无现有 token 可刷新，请先生成。")
            return redirect(url_for('main.tokens'))

        token = create_or_update_game_token(user_id)
        flash(f"Game token 已刷新！旧 token 已失效。新Token为\n{token}")
        logger.info(f"Game token refreshed for user_id={user_id}")
    except Exception as e:
        logger.error(f"Failed to refresh token for user_id={user_id}: {e}")
        flash("刷新 token 失败，请重试。")

    return redirect(url_for('main.tokens'))


@main_bp.route('/tokens/revoke', methods=['POST'])
def revoke_token():
    """撤销当前 token"""
    if 'user_id' not in session:
        return jsonify({"error": "未登录"}), 401

    user_id = session['user_id']
    if not validate_user_id(user_id):
        session.clear()
        return jsonify({"error": "会话异常"}), 401

    try:
        result = revoke_game_token(user_id)
        if result:
            flash("Game token 已撤销。")
            logger.info(f"Game token revoked via UI for user_id={user_id}")
        else:
            flash("未找到可撤销的 token。")
    except Exception as e:
        logger.error(f"Failed to revoke token for user_id={user_id}: {e}")
        flash("撤销 token 失败。")

    return redirect(url_for('main.tokens'))


@main_bp.route('/logout')
def logout():
    session.clear()
    flash('已登出')
    return redirect(url_for('main.index'))

@main_bp.route('/endorse', methods=['POST'])
def endorse_user():
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('auth.login'))

    endorser_id = session['user_id']

    # 从表单获取 endorsee_id
    endorsee_id = request.form.get('endorsee_id', '').strip()

    if not endorsee_id:
        flash('请输入被验证用户的 UUID')
        return redirect(url_for('main.dashboard'))

    if not validate_user_id(endorser_id) or not validate_user_id(endorsee_id):
        flash('无效的用户 ID')
        return redirect(url_for('main.dashboard'))

    if endorser_id == endorsee_id:
        flash('不能验证自己')
        return redirect(url_for('main.dashboard'))

    try:
        handle_user_endorsement(endorser_id, endorsee_id)
        flash('验证成功！')
    except Exception as e:
        logger.error(f"Endorsement failed: {e}")
        flash(f'{e}')

    return redirect(url_for('main.dashboard'))