from models.database import get_db_cursor
from models.reputation import update_reputation, on_user_ban, cancel_deletion
from services.reputation_service import handle_user_ban
from utils.validators import validate_user_id

def ban_user(admin_id, user_id_to_ban):
    validate_user_id(admin_id)
    validate_user_id(user_id_to_ban)
    
    with get_db_cursor() as cursor:
        cursor.execute("SELECT username FROM taUsers WHERE id = %s", (user_id_to_ban,))
        user = cursor.fetchone()
        if not user:
            raise ValueError("用户不存在")
        
        update_reputation(
            user_id=user_id_to_ban,
            change_type='penalty',
            amount=-100,
            related_user_id=admin_id,
            description=f"被管理员 {admin_id} 封禁",
            cursor=cursor
        )
        
        # 传入 cursor，确保在同一个事务中
        handle_user_ban(user_id_to_ban, cursor=cursor)

def unban_user(admin_id, user_id_to_unban):
    """
    撤销封禁用户（将声望分数恢复到基础分数）
    """
    validate_user_id(admin_id)
    validate_user_id(user_id_to_unban)
    
    with get_db_cursor() as cursor:
        cursor.execute("SELECT username FROM taUsers WHERE id = %s", (user_id_to_unban,))
        user = cursor.fetchone()
        if not user:
            raise ValueError("用户不存在")
        
        # 检查用户是否真的被封禁了（声望为0）
        cursor.execute("SELECT score FROM taUsersReputation WHERE user_id = %s", (user_id_to_unban,))
        reputation = cursor.fetchone()
        if not reputation or reputation['score'] != 0:
            raise ValueError("该用户未被封禁")
        
        # 恢复声望到基础分数（例如50分）
        base_score = 50
        old_score = reputation['score'] if reputation else 0
        
        cursor.execute("""
            UPDATE taUsersReputation
            SET score = %s, last_updated = NOW()
            WHERE user_id = %s
        """, (base_score, user_id_to_unban))
        
        # 记录撤销封禁的日志
        cursor.execute("""
            INSERT INTO taUsersReputationLogs 
            (user_id, change_type, change_amount, old_score, new_score, related_user_id, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id_to_unban, 
            'unbanned_by_admin', 
            base_score - old_score, 
            old_score, 
            base_score, 
            admin_id,
            f"被管理员 {admin_id} 撤销封禁"
        ))
        
        # 取消删除计划（如果存在）
        cancel_deletion(user_id_to_unban, cursor)

def toggle_admin_status(admin_id, user_id_to_toggle):
    """切换管理员权限"""
    validate_user_id(admin_id)
    validate_user_id(user_id_to_toggle)
    
    with get_db_cursor() as cursor:
        cursor.execute("SELECT is_admin FROM taUsers WHERE id = %s", (user_id_to_toggle,))
        user = cursor.fetchone()
        if not user:
            raise ValueError("用户不存在")
        
        new_admin_status = not user['is_admin']
        cursor.execute("UPDATE taUsers SET is_admin = %s WHERE id = %s", (new_admin_status, user_id_to_toggle))
        
        return new_admin_status

def get_all_users(page=1, per_page=20, search_query=None):
    """获取所有用户列表"""
    if page < 1:
        page = 1
    offset = (page - 1) * per_page
    
    with get_db_cursor() as cursor:
        # 构建查询语句
        base_query = """
            SELECT 
                u.id, u.username, u.nickname, u.is_2fa_enabled, u.is_admin, u.created_at, u.updated_at, u.last_login,
                r.score as reputation_score,
                g.github_login
            FROM taUsers u
            LEFT JOIN taUsersReputation r ON u.id = r.user_id
            LEFT JOIN taUserGitHub g ON u.id = g.user_id
        """
        
        count_query = "SELECT COUNT(*) as total FROM taUsers u"
        
        params = []
        count_params = []
        
        if search_query:
            search_filter = " WHERE u.username ILIKE %s OR u.nickname ILIKE %s OR u.id::text ILIKE %s"
            base_query += search_filter
            count_query += search_filter
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param, search_param])
            count_params.extend([search_param, search_param, search_param])
        
        base_query += " ORDER BY u.created_at DESC LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        
        # 获取用户列表
        cursor.execute(base_query, params)
        users = cursor.fetchall()
        
        # 获取总数
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']
        
        # 对每个用户检查是否被封禁
        from models.reputation import is_user_banned
        for user in users:
            user['is_banned'] = is_user_banned(user['id'])
        
        return users, total
