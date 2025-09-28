import psycopg2
import psycopg2.extras
import bcrypt
import uuid
from datetime import datetime, timedelta
import random
import string

def create_test_users():
    # 数据库连接配置
    DATABASE_URL = "postgresql://teealloytest:test@localhost:5432/teealloydb"
    
    try:
        # 连接数据库
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("✅ 数据库连接成功")
        
        # 生成测试用户数据
        test_users = []
        for i in range(50):  # 创建50个测试用户
            username = f"testuser{i:03d}"
            nickname = f"测试用户{i:03d}"
            password_hash = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            user_data = {
                'id': str(uuid.uuid4()),
                'username': username,
                'nickname': nickname,
                'password_hash': password_hash,
                'created_at': datetime.now() - timedelta(days=random.randint(1, 365)),
                'is_admin': False,
                'is_2fa_enabled': random.choice([True, False])
            }
            test_users.append(user_data)
        
        print(f"📝 准备创建 {len(test_users)} 个测试用户")
        
        # 批量插入用户
        insert_query = """
            INSERT INTO taUsers (id, username, nickname, password_hash, created_at, is_2fa_enabled, is_admin)
            VALUES (%(id)s, %(username)s, %(nickname)s, %(password_hash)s, %(created_at)s, %(is_2fa_enabled)s, %(is_admin)s)
        """
        
        cursor.executemany(insert_query, test_users)
        conn.commit()
        print(f"✅ 成功插入 {len(test_users)} 个测试用户")
        
        # 为部分用户创建声望记录
        reputation_users = []
        for user in test_users[:40]:  # 为前40个用户创建声望记录
            score = random.randint(0, 100)
            is_contributor = random.choice([True, False])
            has_github_login = random.choice([True, False])
            
            reputation_data = {
                'user_id': user['id'],
                'score': score,
                'is_contributor': is_contributor,
                'has_github_login': has_github_login,
                'created_at': datetime.now(),
                'last_updated': datetime.now()
            }
            reputation_users.append(reputation_data)
        
        insert_reputation_query = """
            INSERT INTO taUsersReputation (user_id, score, is_contributor, has_github_login, created_at, last_updated)
            VALUES (%(user_id)s, %(score)s, %(is_contributor)s, %(has_github_login)s, %(created_at)s, %(last_updated)s)
        """
        
        cursor.executemany(insert_reputation_query, reputation_users)
        conn.commit()
        print(f"✅ 成功为 {len(reputation_users)} 个用户创建声望记录")
        
        # 为部分用户创建声望日志
        reputation_logs = []
        for user in reputation_users:
            log_types = ['initial', 'github_login', 'endorsed_by_user', 'first_2fa_verification']
            for _ in range(random.randint(1, 5)):  # 为每个用户创建1-5条日志
                log_data = {
                    'user_id': user['user_id'],
                    'change_type': random.choice(log_types),
                    'change_amount': random.randint(-20, 50),
                    'old_score': max(0, user['score'] - random.randint(0, 30)),
                    'new_score': user['score'],
                    'description': f"测试日志 - {random.choice(['注册', 'GitHub登录', '获得验证', '2FA验证'])}",
                    'created_at': datetime.now() - timedelta(days=random.randint(0, 30))
                }
                reputation_logs.append(log_data)
        
        insert_log_query = """
            INSERT INTO taUsersReputationLogs (user_id, change_type, change_amount, old_score, new_score, description, created_at)
            VALUES (%(user_id)s, %(change_type)s, %(change_amount)s, %(old_score)s, %(new_score)s, %(description)s, %(created_at)s)
        """
        
        cursor.executemany(insert_log_query, reputation_logs)
        conn.commit()
        print(f"✅ 成功创建 {len(reputation_logs)} 条声望日志")
        
        # 为部分用户启用2FA
        users_with_2fa = [user for user in test_users if user['is_2fa_enabled']]
        totp_records = []
        
        for user in users_with_2fa:
            # 模拟加密数据（实际使用时会被加密）
            totp_secret_encrypted = f"encrypted_secret_{user['id']}".encode('utf-8')
            backup_codes = ','.join([f"backup_code_{i}" for i in range(5)])
            backup_codes_encrypted = backup_codes.encode('utf-8')
            
            totp_data = {
                'user_id': user['id'],
                'totp_secret_encrypted': totp_secret_encrypted,
                'backup_codes_encrypted': backup_codes_encrypted,
                'backup_codes_salt': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            totp_records.append(totp_data)
        
        if totp_records:
            insert_totp_query = """
                INSERT INTO taUserTOTP (user_id, totp_secret_encrypted, backup_codes_encrypted, backup_codes_salt, created_at, updated_at)
                VALUES (%(user_id)s, %(totp_secret_encrypted)s, %(backup_codes_encrypted)s, %(backup_codes_salt)s, %(created_at)s, %(updated_at)s)
            """
            
            cursor.executemany(insert_totp_query, totp_records)
            conn.commit()
            print(f"✅ 为 {len(totp_records)} 个用户创建2FA记录")
        
        # 验证插入结果
        cursor.execute("SELECT COUNT(*) as total FROM taUsers")
        total_users = cursor.fetchone()['total']
        print(f"📊 数据库中总用户数: {total_users}")
        
        cursor.execute("SELECT COUNT(*) as total FROM taUsersReputation")
        total_reputation = cursor.fetchone()['total']
        print(f"📊 声望记录数: {total_reputation}")
        
        cursor.execute("SELECT COUNT(*) as total FROM taUsersReputationLogs")
        total_logs = cursor.fetchone()['total']
        print(f"📊 声望日志数: {total_logs}")
        
        cursor.execute("SELECT COUNT(*) as total FROM taUserTOTP")
        total_totp = cursor.fetchone()['total']
        print(f"📊 2FA记录数: {total_totp}")
        
        # 显示前10个用户作为验证
        cursor.execute("SELECT id, username, nickname, is_admin, is_2fa_enabled, created_at FROM taUsers ORDER BY created_at DESC LIMIT 10")
        recent_users = cursor.fetchall()
        print("\n📋 最近创建的用户:")
        for user in recent_users:
            print(f"  - {user['username']} ({user['nickname']}) - ID: {user['id'][:8]}... - 2FA: {'✓' if user['is_2fa_enabled'] else '✗'} - 管理员: {'✓' if user['is_admin'] else '✗'}")
        
        cursor.close()
        conn.close()
        print("\n✅ 测试用户创建完成!")
        
    except Exception as e:
        print(f"❌ 创建测试用户时出错: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

def clean_test_users():
    """清理测试用户（可选）"""
    DATABASE_URL = "postgresql://teealloytest:test@localhost:5432/teealloydb"
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # 删除测试用户（用户名以testuser开头的）
        cursor.execute("DELETE FROM taUserTOTP WHERE user_id IN (SELECT id FROM taUsers WHERE username LIKE 'testuser%')")
        cursor.execute("DELETE FROM taUsersReputationLogs WHERE user_id IN (SELECT id FROM taUsers WHERE username LIKE 'testuser%')")
        cursor.execute("DELETE FROM taUsersReputation WHERE user_id IN (SELECT id FROM taUsers WHERE username LIKE 'testuser%')")
        cursor.execute("DELETE FROM taUsers WHERE username LIKE 'testuser%'")
        
        conn.commit()
        print("✅ 测试用户已清理完毕")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ 清理测试用户时出错: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

def create_users_for_immediate_deletion():
    """
    创建一批声望为0的测试用户，并立即将其 deletion_due 设置为1小时前
    以便自动删除任务能立刻处理它们
    """
    DATABASE_URL = "postgresql://teealloytest:test@localhost:5432/teealloydb"
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("🔥 开始创建需要立即被删除的用户...")

        # 创建10个需要立即被删除的用户
        deletion_users = []
        for i in range(10):
            username = f"deleteuser{i:03d}"
            nickname = f"待删用户{i:03d}"
            password_hash = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            user_data = {
                'id': str(uuid.uuid4()),
                'username': username,
                'nickname': nickname,
                'password_hash': password_hash,
                'created_at': datetime.now() - timedelta(days=random.randint(30, 365)),
                'is_admin': False,
                'is_2fa_enabled': random.choice([True, False])
            }
            deletion_users.append(user_data)
        
        print(f"📝 准备创建 {len(deletion_users)} 个待删除用户")

        # 插入用户
        insert_user_query = """
            INSERT INTO taUsers (id, username, nickname, password_hash, created_at, is_2fa_enabled, is_admin)
            VALUES (%(id)s, %(username)s, %(nickname)s, %(password_hash)s, %(created_at)s, %(is_2fa_enabled)s, %(is_admin)s)
        """
        cursor.executemany(insert_user_query, deletion_users)
        conn.commit()
        print(f"✅ 成功插入 {len(deletion_users)} 个待删除用户")

        # 为这些用户创建声望记录（score = 0）
        reputation_data_list = []
        for user in deletion_users:
            rep_data = {
                'user_id': user['id'],
                'score': 0,
                'is_contributor': False,
                'has_github_login': False,
                'created_at': datetime.now(),
                'last_updated': datetime.now()
            }
            reputation_data_list.append(rep_data)

        insert_reputation_query = """
            INSERT INTO taUsersReputation (user_id, score, is_contributor, has_github_login, created_at, last_updated)
            VALUES (%(user_id)s, %(score)s, %(is_contributor)s, %(has_github_login)s, %(created_at)s, %(last_updated)s)
        """
        cursor.executemany(insert_reputation_query, reputation_data_list)
        conn.commit()
        print(f"✅ 为 {len(reputation_data_list)} 个用户创建声望为0的记录")

        # 立即加入 taPendingDeletion，且 deletion_due = 1小时前（已过期）
        pending_deletion_data = []
        for user in deletion_users:
            pending_deletion_data.append({
                'user_id': user['id'],
                'marked_at': datetime.now(),
                'deletion_due': datetime.now() - timedelta(hours=1),  # 已过期！
                'is_processed': False
            })

        insert_pending_query = """
            INSERT INTO taPendingDeletion (user_id, marked_at, deletion_due, is_processed)
            VALUES (%(user_id)s, %(marked_at)s, %(deletion_due)s, %(is_processed)s)
        """
        cursor.executemany(insert_pending_query, pending_deletion_data)
        conn.commit()
        print(f"✅ 已将 {len(pending_deletion_data)} 个用户加入待删除队列，deletion_due 已过期")

        # 验证：查询已加入待删除的用户
        cursor.execute("""
            SELECT pd.user_id, u.username, pd.deletion_due, pd.is_processed
            FROM taPendingDeletion pd
            JOIN taUsers u ON u.id = pd.user_id
            WHERE pd.user_id = ANY(%s::uuid[])
        """, ([u['id'] for u in deletion_users],))

        result = cursor.fetchall()
        print("\n🕒 待删除用户列表（deletion_due 已过期）:")
        for row in result:
            print(f"  - {row['username']} | deletion_due: {row['deletion_due']} | is_processed: {row['is_processed']}")

        cursor.close()
        conn.close()
        print("\n🎉 所有待删除用户创建完成！现在运行自动删除任务即可清除他们。")

    except Exception as e:
        print(f"❌ 创建待删除用户失败: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    print("🚀 开始创建测试用户...")
    create_test_users()
    create_users_for_immediate_deletion()