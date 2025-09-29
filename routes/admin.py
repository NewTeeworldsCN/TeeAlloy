from flask import Blueprint, request, render_template, session, flash, redirect, url_for
from utils.validators import validate_user_id
from utils import generate_api_key
from services.admin_service import get_all_users, ban_user, unban_user, toggle_admin_status
from models.user import get_user_by_id
from models.whitelist import (
    add_whitelist_server,
    remove_whitelist_server,
    get_all_whitelist_servers,
    get_whitelist_by_address
)

admin_bp = Blueprint('admin', __name__)

def require_admin(f):
    """装饰器：检查用户是否为管理员"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录')
            return redirect(url_for('auth.login'))
        
        user_id = session['user_id']
        if not validate_user_id(user_id):
            session.clear()
            flash('会话异常')
            return redirect(url_for('auth.login'))
        
        from models.user import get_user_by_id
        user = get_user_by_id(user_id)
        if not user or not user['is_admin']:
            flash('权限不足')
            # 修复这里：使用正确的端点名称
            return redirect(url_for('main.dashboard'))  # 确保这个端点存在
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/admin')
@require_admin
def admin_panel():
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', '')
    
    users, total = get_all_users(page=page, per_page=20, search_query=search_query)
    total_pages = (total + 19) // 20  # 向上取整
    
    return render_template('admin_panel.html', 
                         users=users, 
                         current_page=page, 
                         total_pages=total_pages, 
                         total_users=total,
                         search_query=search_query)

@admin_bp.route('/admin/ban/<user_id>', methods=['POST'])
@require_admin
def admin_ban_user(user_id):
    try:
        user_id = validate_user_id(user_id)
        admin_id = session['user_id']
        ban_user(admin_id, user_id)
        flash(f'用户 {user_id} 已被封禁')
    except Exception as e:
        flash(f'封禁失败: {str(e)}')
    
    return redirect(url_for('admin.admin_panel'))

@admin_bp.route('/admin/unban/<user_id>', methods=['POST'])
@require_admin
def admin_unban_user(user_id):
    """
    撤销封禁用户路由
    """
    try:
        user_id = validate_user_id(user_id)
        admin_id = session['user_id']
        unban_user(admin_id, user_id)
        flash(f'用户 {user_id} 已被撤销封禁')
    except Exception as e:
        flash(f'撤销封禁失败: {str(e)}')
    
    return redirect(url_for('admin.admin_panel'))

@admin_bp.route('/admin/toggle-admin/<user_id>', methods=['POST'])
@require_admin
def admin_toggle_admin(user_id):
    try:
        user_id = validate_user_id(user_id)
        admin_id = session['user_id']
        new_status = toggle_admin_status(admin_id, user_id)
        action = "授予" if new_status else "撤销"
        flash(f'已{action}用户 {user_id} 管理员权限')
    except Exception as e:
        flash(f'操作失败: {str(e)}')
    
    return redirect(url_for('admin.admin_panel'))

# ========================
# 白名单管理
# ========================

@admin_bp.route('/admin/whitelist')
@require_admin
def whitelist_management():
    """白名单管理页面"""
    try:
        servers = get_all_whitelist_servers()  # 来自 models.whitelist
        # 按 server_address 分组
        from collections import defaultdict
        grouped = defaultdict(list)
        for s in servers:
            # 判断是否是“刚刚创建”的记录（用于一次性显示明文）
            show_plaintext = 'new_api_key_hash' in session and session['new_api_key_hash'] == s['api_key_hash']
            item = {
                'api_key_hash': s['api_key_hash'],
                'created_at': s['created_at'],
                'show_plaintext': show_plaintext,
                'plaintext_api_key': session.get('new_api_key_plaintext') if show_plaintext else None
            }
            grouped[s['server_address']].append(item)

        # 清除一次性 session（只显示一次）
        if 'new_api_key_hash' in session:
            session.pop('new_api_key_hash', None)
            session.pop('new_api_key_plaintext', None)

        return render_template('admin_whitelist.html', 
                             grouped_servers=dict(grouped),
                             total_count=len(servers))
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Failed to load whitelist: {e}")
        flash("加载白名单失败")
        return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/admin/whitelist/add', methods=['POST'])
@require_admin
def add_whitelist_entry():
    """添加白名单条目（系统自动生成 API Key）"""
    try:
        server_addr = request.form.get('server_address')
        
        if not server_addr:
            flash("服务器地址为必填项")
            return redirect(url_for('admin.whitelist_management'))

        if len(server_addr) > 45:
            flash("服务器地址过长")
            return redirect(url_for('admin.whitelist_management'))

        plaintext_key, hashed_key = generate_api_key()

        success = add_whitelist_server(server_addr.strip(), hashed_key)
        if success:
            # ✅ 一次性在页面上显示明文 Key
            session['new_api_key_hash'] = hashed_key
            session['new_api_key_plaintext'] = plaintext_key
            flash(f"✅ 成功添加白名单: {server_addr}")
        else:
            flash(f"⚠️ 该地址已存在，无需重复添加")

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Add whitelist failed: {e}")
        flash(f"添加失败: {str(e)}")

    return redirect(url_for('admin.whitelist_management'))


@admin_bp.route('/admin/whitelist/remove/<path:server_addr>/<api_key_hash>')
def remove_whitelist_entry(server_addr, api_key_hash):
    """
    删除白名单条目
    :param server_addr: URL-encoded server address（支持 / 和 : 的 IPv6）
    :param api_key_hash: SHA-256 哈希值
    """
    try:
        # 验证 hash 格式
        if not api_key_hash or len(api_key_hash) != 64 or not api_key_hash.isalnum():
            flash("无效的 API Key Hash")
            return redirect(url_for('admin.whitelist_management'))

        removed = remove_whitelist_server(server_addr, api_key_hash)
        if removed:
            flash(f"🗑️ 已删除白名单记录: {server_addr}")
        else:
            flash(f"🔍 未找到匹配的记录")

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Remove whitelist failed: {e}")
        flash(f"删除失败: {str(e)}")

    return redirect(url_for('admin.whitelist_management'))