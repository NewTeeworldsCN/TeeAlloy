# models/database.py

import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from config import Config
import logging

# 获取 logger
logger = logging.getLogger(__name__)

# 全局连接池
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=Config.DB_MIN_CONN,
        maxconn=Config.DB_MAX_CONN,
        dsn=Config.DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    print(f"数据库连接池已启动: {Config.DB_MIN_CONN} ~ {Config.DB_MAX_CONN} 个连接")
except Exception as e:
    print(f"无法创建数据库连接池: {e}")
    raise


def is_connection_usable(conn):
    """
    检查数据库连接是否仍然可用，并清理未完成的事务
    """
    try:
        if conn.closed:
            return False

        # 清理未完成的事务
        if conn.get_transaction_status() != 0:  # 非 IDLE 状态
            try:
                conn.rollback()
            except Exception as e:
                logger.warning(f"回滚未完成事务失败: {e}")
                return False

        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        return True
    except Exception as e:
        logger.warning(f"连接检测失败: {e}")
        try:
            conn.close()
        except:
            pass
        return False


def get_db():
    """
    从连接池获取数据库连接，并确保连接可用
    """
    try:
        conn = db_pool.getconn()
        if is_connection_usable(conn):
            conn.autocommit = False
            return conn
        else:
            logger.warning("检测到无效数据库连接，正在重建...")
            try:
                db_pool.putconn(conn, close=True)
            except Exception as e:
                logger.error(f"归还坏连接失败: {e}")
    except Exception as e:
        logger.warning(f"从连接池获取连接失败: {e}")

    # 重建新连接
    try:
        logger.info("正在创建新数据库连接...")
        conn = psycopg2.connect(
            Config.DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        conn.autocommit = False
        return conn
    except Exception as e:
        logger.error(f"无法创建新数据库连接: {e}")
        raise


def close_db(conn):
    """
    将连接归还给连接池，确保事务已清理
    """
    if not conn or conn.closed:
        return

    try:
        # 确保事务已结束
        if conn.get_transaction_status() != 0:
            try:
                conn.rollback()
                logger.debug("强制回滚未完成事务")
            except Exception as e:
                logger.warning(f"回滚事务失败: {e}")

        # 归还连接
        db_pool.putconn(conn)
        logger.debug("连接已归还到池")
    except psycopg2.pool.PoolError as e:
        logger.error(f"连接池错误（池满或无效）: {e}，关闭连接")
        try:
            conn.close()
        except Exception as close_e:
            logger.error(f"关闭连接失败: {close_e}")
    except Exception as e:
        logger.error(f"归还连接失败: {e}，关闭连接")
        try:
            conn.close()
        except Exception as close_e:
            logger.error(f"关闭连接失败: {close_e}")


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
            try:
                conn.commit()
                logger.debug("事务已提交")
            except Exception as e:
                try:
                    conn.rollback()
                    logger.debug("提交失败，已回滚")
                except:
                    pass
                raise e
        else:
            try:
                conn.rollback()
                logger.debug("事务已回滚（只读模式）")
            except Exception as e:
                logger.warning(f"回滚失败: {e}")

    except Exception as e:
        if conn:
            try:
                conn.rollback()
                logger.debug("异常回滚")
            except Exception as rollback_e:
                logger.warning(f"事务回滚失败: {rollback_e}")
        logger.error(f"数据库操作失败: {e}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
                logger.debug("游标已关闭")
            except Exception as e:
                logger.warning(f"关闭游标失败: {e}")
        if conn:
            close_db(conn)


# 关闭连接池
import atexit

@atexit.register
def close_db_pool():
    global db_pool
    if 'db_pool' in globals():
        try:
            db_pool.closeall()
            print("🔗 数据库连接池已关闭")
        except Exception as e:
            print(f"❌ 关闭连接池时出错: {e}")