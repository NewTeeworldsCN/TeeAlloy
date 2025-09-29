from models.database import get_db_cursor, get_db, close_db
from utils.validators import validate_user_id
import utils

from models.database import get_db_cursor, get_db, close_db

def process_pending_deletions(logger):
    """
    自动处理待删除用户：删除到期的用户账户
    """
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 查询所有到期且未处理的删除请求
        cursor.execute("""
            SELECT user_id FROM taPendingDeletion
            WHERE deletion_due <= NOW() 
              AND is_processed = FALSE
            FOR UPDATE SKIP LOCKED  -- 避免并发问题
        """)

        rows = cursor.fetchall()
        if not rows:
            logger.info("没有待处理的删除任务")
            return

        deleted_count = 0
        for row in rows:
            user_id = row['user_id']
            try:
                # 开始删除用户数据（按外键依赖顺序）
                # 注意：taUsersReputation、taUserGitHub 等表有外键引用 taUsers

                # 方法1：依赖 ON DELETE CASCADE（推荐）
                # 如果所有表都设置了 ON DELETE CASCADE，则只需删 taUsers
                cursor.execute("DELETE FROM taUsers WHERE id = %s", (user_id,))

                # 标记为已处理
                cursor.execute("""
                    UPDATE taPendingDeletion 
                    SET is_processed = TRUE 
                    WHERE user_id = %s
                """, (user_id,))

                logger.info(f"已自动删除用户: {user_id}")
                deleted_count += 1

            except Exception as e:
                logger.error(f"删除用户 {user_id} 失败: {e}")
                continue

        conn.commit()
        logger.info(f"本次任务完成，共删除 {deleted_count} 个用户")

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"处理待删除用户时发生严重错误: {e}")
    finally:
        if conn:
            close_db(conn)

def update_reputation(user_id, change_type, amount, related_user_id=None, description="", cursor=None):
    """
    更新用户声望
    cursor: 如果传入游标，则在现有事务中操作，否则创建新事务
    """
    validate_user_id(user_id)
    if related_user_id:
        validate_user_id(related_user_id)
    
    if cursor:
        _update_reputation_with_cursor(cursor, user_id, change_type, amount, related_user_id, description)
    else:
        with get_db_cursor() as new_cursor:
            _update_reputation_with_cursor(new_cursor, user_id, change_type, amount, related_user_id, description)

def _update_reputation_with_cursor(cursor, user_id, change_type, amount, related_user_id, description):
    # 获取当前声望
    cursor.execute("""
        SELECT score, is_contributor, has_github_login
        FROM taUsersReputation
        WHERE user_id = %s FOR UPDATE
    """, (user_id,))
    row = cursor.fetchone()
    old_score = row['score'] if row else 0
    is_contributor = row['is_contributor'] if row else False
    has_github_login = row['has_github_login'] if row else False

    new_score = max(0, min(100, old_score + amount))

    # 自动推导布尔字段
    if change_type == 'github_login':
        has_github_login = True
    elif change_type == 'teeworlds_contributor':
        is_contributor = True

    # 插入或更新声望表
    if not row:
        cursor.execute("""
            INSERT INTO taUsersReputation (user_id, score, is_contributor, has_github_login)
            VALUES (%s, %s, %s, %s)
        """, (user_id, new_score, is_contributor, has_github_login))
    else:
        cursor.execute("""
            UPDATE taUsersReputation
            SET score = %s, is_contributor = %s, has_github_login = %s, last_updated = NOW()
            WHERE user_id = %s
        """, (new_score, is_contributor, has_github_login, user_id))

    # 记录日志
    cursor.execute("""
        INSERT INTO taUsersReputationLogs 
        (user_id, change_type, change_amount, old_score, new_score, related_user_id, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, change_type, amount, old_score, new_score, related_user_id, description))

    # 检查是否需要加入待删除队列
    if new_score == 0:
        schedule_for_deletion(user_id, cursor)
    else:
        cancel_deletion(user_id, cursor)

def schedule_for_deletion(user_id, cursor=None):
    validate_user_id(user_id)
    if cursor:
        cursor.execute("""
            INSERT INTO taPendingDeletion (user_id, deletion_due)
            VALUES (%s, NOW() + INTERVAL '7 days')
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id,))
    else:
        with get_db_cursor() as new_cursor:
            new_cursor.execute("""
                INSERT INTO taPendingDeletion (user_id, deletion_due)
                VALUES (%s, NOW() + INTERVAL '7 days')
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id,))

def cancel_deletion(user_id, cursor=None):
    validate_user_id(user_id)
    if cursor:
        cursor.execute("DELETE FROM taPendingDeletion WHERE user_id = %s", (user_id,))
    else:
        with get_db_cursor() as new_cursor:
            new_cursor.execute("DELETE FROM taPendingDeletion WHERE user_id = %s", (user_id,))

def get_user_reputation(user_id):
    """获取用户声望信息"""
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM taUsersReputation WHERE user_id = %s", (user_id,))
        return cursor.fetchone()

def make_full_reputation(user_id):
    validate_user_id(user_id)
    update_reputation(
        user_id=user_id,
        change_type='teeworlds_contributor',
        amount=100,
        description="用户是 Teeworlds 项目贡献者"
    )

def on_github_login(user_id, github_info):
    validate_user_id(user_id)
    with get_db_cursor() as cursor:
        # 绑定 GitHub
        cursor.execute("""
            INSERT INTO taUserGitHub (user_id, github_id, github_login, avatar_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                github_id = EXCLUDED.github_id,
                github_login = EXCLUDED.github_login,
                avatar_url = EXCLUDED.avatar_url
        """, (user_id, github_info['id'], github_info['login'], github_info['avatar_url']))

        # +30 声望
        update_reputation(
            user_id=user_id,
            change_type='github_login',
            amount=30,
            description=f"通过 GitHub 登录: {github_info['login']}"
        )

        # 检查是否是 Teeworlds 贡献者
        if utils.is_teeworlds_contributor(github_info['login']):
            make_full_reputation(user_id)

def endorse_user(endorser_id, endorsee_id):
    validate_user_id(endorser_id)
    validate_user_id(endorsee_id)
    
    if endorser_id == endorsee_id:
        raise ValueError("不能验证自己")

    with get_db_cursor() as cursor:
        # 检查验证者声望 ≥ 50
        cursor.execute("SELECT score FROM taUsersReputation WHERE user_id = %s", (endorser_id,))
        endorser_reputation = cursor.fetchone()
        if not endorser_reputation or endorser_reputation['score'] < 50:
            raise PermissionError("声望不足，无法验证他人")

        # 查询被验证者的当前声望
        cursor.execute("SELECT score FROM taUsersReputation WHERE user_id = %s", (endorsee_id,))
        endorsee_reputation = cursor.fetchone()
        if not endorsee_reputation:
            raise ValueError("被验证用户没有声望记录，无法验证")

        # 核心新增逻辑：验证者声望必须 >= 被验证者声望
        if endorser_reputation['score'] < endorsee_reputation['score']:
            raise PermissionError("无法验证声望高于自己的用户")

        # 检查被验证者是否已被任何人验证过（全局唯一验证）
        cursor.execute("""
            SELECT 1 FROM taCreditEndorsements 
            WHERE endorsee_id = %s AND is_valid = TRUE
        """, (endorsee_id,))
        if cursor.fetchone():
            raise ValueError("该用户已被验证过，无法再次验证")

        # 检查当前验证者是否已验证过该用户
        cursor.execute("""
            SELECT is_valid FROM taCreditEndorsements 
            WHERE endorser_id = %s AND endorsee_id = %s
        """, (endorser_id, endorsee_id))
        existing = cursor.fetchone()
        if existing:
            raise ValueError("已验证过该用户")

        # 创建验证记录
        cursor.execute("""
            INSERT INTO taCreditEndorsements (endorsee_id, endorser_id)
            VALUES (%s, %s)
        """, (endorsee_id, endorser_id))

        # 被验证者 +30 声望（或 +50 如果验证者声望 >80）
        score = 30
        if endorser_reputation['score'] > 80:
            score = 50

        update_reputation(
            user_id=endorsee_id,
            change_type='endorsed_by_user',
            amount=score,
            related_user_id=endorser_id,
            description=f"被用户 {endorser_id} 验证"
        )
        return
    raise PermissionError("数据库连接错误")

def on_user_ban(banned_user_id, cursor=None):
    """
    处理用户被封禁后的逻辑
    cursor: 可选，用于在现有事务中执行
    """
    validate_user_id(banned_user_id)
    own_cursor = False
    if not cursor:
        own_cursor = True
        conn = get_db()
        cursor = conn.cursor()

    try:
        # 查找所有由该用户验证的记录
        cursor.execute("""
            SELECT endorsee_id FROM taCreditEndorsements
            WHERE endorser_id = %s AND is_valid = TRUE
        """, (banned_user_id,))
        
        for row in cursor.fetchall():
            endorsee_id = row['endorsee_id']
            validate_user_id(endorsee_id)  # 验证被验证者ID
            
            cursor.execute("""
                UPDATE taCreditEndorsements
                SET is_valid = FALSE, invalidated_at = NOW()
                WHERE endorser_id = %s AND endorsee_id = %s
            """, (banned_user_id, endorsee_id))
            
            update_reputation(
                user_id=endorsee_id,
                change_type='endorsement_revoked',
                amount=-30,
                related_user_id=banned_user_id,
                description="因验证者被封禁，声望被撤销",
                cursor=cursor  # 复用事务
            )
        
        # 验证者自身声望也下降
        update_reputation(
            user_id=banned_user_id,
            change_type='penalty',
            amount=-20,
            description="因封禁被扣除声望",
            cursor=cursor  # 复用事务
        )

        if own_cursor:
            conn.commit()
    except Exception as e:
        if own_cursor:
            conn.rollback()
        raise e
    finally:
        if own_cursor:
            close_db(conn)

def is_user_banned(user_id):
    """
    检查用户是否被封禁
    通过检查声望日志中是否有封禁记录且当前声望为0来判断
    """
    validate_user_id(user_id)
    
    with get_db_cursor() as cursor:
        # 获取当前声望分数
        cursor.execute("SELECT score FROM taUsersReputation WHERE user_id = %s", (user_id,))
        reputation = cursor.fetchone()
        
        if not reputation or reputation['score'] != 0:
            return False  # 声望不为0，肯定没被封禁
        
        # 检查是否有封禁记录
        cursor.execute("""
            SELECT EXISTS(
                SELECT 1 FROM taUsersReputationLogs 
                WHERE user_id = %s 
                AND change_type = 'penalty' 
                AND description LIKE %s
            ) AS has_ban_record
        """, (user_id, '%封禁%'))
        result = cursor.fetchone()
        
        return result['has_ban_record'] if result else False
