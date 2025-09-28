# models/database.py

import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from config import Config

# 全局连接池
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=Config.DB_MIN_CONN,
        maxconn=Config.DB_MAX_CONN,
        dsn=Config.DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    print(f"✅ 数据库连接池已启动: {Config.DB_MIN_CONN} ~ {Config.DB_MAX_CONN} 个连接")
except Exception as e:
    print(f"❌ 无法创建数据库连接池: {e}")
    raise


def get_db():
    """从连接池获取数据库连接"""
    try:
        conn = db_pool.getconn()
        conn.autocommit = False
        return conn
    except Exception as e:
        try:
            conn = psycopg2.connect(Config.DATABASE_URL)
            conn.autocommit = False
            return conn
        except Exception as e2:
            raise e2


def close_db(conn):
    """将连接归还给连接池"""
    if conn and not conn.closed:
        try:
            db_pool.putconn(conn)
        except psycopg2.pool.PoolError:
            try:
                conn.close()
            except:
                pass


@contextmanager
def get_db_cursor(commit_on_success=True):
    """
    获取数据库游标上下文管理器
    :param commit_on_success: 是否在退出时自动提交事务（默认 True）
    """
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        yield cursor

        if commit_on_success:
            conn.commit()
        else:
            # 只读模式或手动控制事务
            conn.rollback()  # 避免未提交事务占用连接
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise e
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            close_db(conn)


# 关闭连接池
import atexit

@atexit.register
def close_db_pool():
    global db_pool
    if 'db_pool' in globals():
        db_pool.closeall()
        print("🔗 数据库连接池已关闭")
