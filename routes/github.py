from flask import Blueprint, request, session, flash, redirect, url_for
from utils.validators import validate_uuid
import secrets
import utils

github_bp = Blueprint('github', __name__)

@github_bp.route('/auth/github')
def github_login():
    """发起 GitHub OAuth 登录流程"""
    redirect_uri = url_for('github.github_callback', _external=True)
    state = secrets.token_urlsafe(32)
    session['github_oauth_state'] = state  # 用于 CSRF 防护
    auth_url = utils.github.get_github_login_url(redirect_uri=redirect_uri, state=state)
    return redirect(auth_url)

@github_bp.route('/auth/github/callback')
def github_callback():
    stored_state = session.pop('github_oauth_state', None)
    received_state = request.args.get('state')
    
    if not stored_state or stored_state != received_state:
        flash('OAuth 状态验证失败，请重试')
        return redirect(url_for('auth.login'))

    error = request.args.get('error')
    if error:
        flash(f'GitHub 登录被拒绝: {error}')
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        flash('未收到授权码')
        return redirect(url_for('auth.login'))

    redirect_uri = url_for('github.github_callback', _external=True)
    access_token = utils.github.exchange_code_for_token(code=code, redirect_uri=redirect_uri)
    if not access_token:
        flash('无法获取 GitHub 访问令牌')
        return redirect(url_for('auth.login'))

    github_info = utils.github.get_github_user_info(access_token)
    if not github_info:
        flash('无法获取 GitHub 用户信息')
        return redirect(url_for('auth.login'))

    github_id = github_info['id']
    github_login = github_info['login']

    try:
        from models.database import get_db_cursor
        with get_db_cursor() as cursor:
            # 检查该 GitHub 账号是否已绑定到某个用户
            cursor.execute("SELECT user_id FROM taUserGitHub WHERE github_id = %s", (github_id,))
            bound_row = cursor.fetchone()

            if bound_row:
                user_id = bound_row['user_id']
                if not validate_uuid(user_id):
                    flash('绑定的用户账户异常')
                    return redirect(url_for('auth.login'))
                
                # 已绑定：直接登录
                cursor.execute("SELECT username, is_2fa_enabled FROM taUsers WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if not user:
                    flash('绑定的用户账户异常')
                    return redirect(url_for('auth.login'))
                
                # 检查是否启用2FA
                if user['is_2fa_enabled']:
                    session['pending_2fa_user_id'] = user_id
                    session['2fa_stage'] = True
                    session.permanent = True
                    flash('GitHub 登录成功，请输入 2FA 验证码')
                    return redirect(url_for('auth.verify_2fa'))
                else:
                    session['user_id'] = user_id
                    session['username'] = user['username']
                    session.permanent = True
                    flash(f'欢迎回来，{github_login}！')
                    return redirect(url_for('main.dashboard'))

            # 未绑定：检查用户是否已登录（主动绑定场景）
            if 'user_id' in session:
                current_user_id = session['user_id']
                if not validate_uuid(current_user_id):
                    session.clear()
                    flash('会话异常')
                    return redirect(url_for('auth.login'))
                
                # 用户已登录，允许绑定 GitHub
                from services.reputation_service import handle_github_login
                handle_github_login(current_user_id, github_info)
                flash('GitHub 账号绑定成功！')
                return redirect(url_for('main.dashboard'))

            # 未绑定且未登录：引导用户先登录或注册
            # 存储 GitHub 信息到 session，用于后续绑定
            session['pending_github_info'] = {
                'id': github_id,
                'login': github_login,
                'avatar_url': github_info.get('avatar_url', ''),
                'name': github_info.get('name') or github_login
            }
            flash('请先登录或注册以绑定 GitHub 账号')
            return redirect(url_for('auth.login'))

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"GitHub 登录处理失败: {e}")
        flash('登录过程中发生错误，请重试')
        return redirect(url_for('auth.login'))
