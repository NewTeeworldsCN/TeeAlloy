# models/database.py

import psycopg2
import psycopg2.extras
import psycopg2.pool
import logging
import threading
import uuid
from contextlib import contextmanager
from config import Config

logger = logging.getLogger(__name__)

# === 线程局部存储：唯一的数据持有者 ===
_tls = threading.local()


def set_connection_context(conn, is_pooled=True):
    """将连接上下文信息存入线程局部变量"""
    cid = str(uuid.uuid4())[:8]
    if not is_pooled:
        cid += "-tmp"

    _tls.current_conn = conn
    _tls.connection_id = cid
    _tls.is_pooled = is_pooled


def get_connection_id() -> str:
    """获取当前线程的连接 ID"""
    return getattr(_tls, 'connection_id', 'unknown')


def is_pooled_connection() -> bool:
    """当前是否使用池化连接"""
    return getattr(_tls, 'is_pooled', False)


def get_current_conn():
    """获取当前线程的连接对象（仅用于调试）"""
    return getattr(_tls, 'current_conn', None)


def _cleanup_tls():
    """清理线程局部变量"""
    for attr in ('current_conn', 'connection_id', 'is_pooled'):
        if hasattr(_tls, attr):
            delattr(_tls, attr)


# === 连接池初始化 ===
db_pool = None

try:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        minconn=Config.DB_MIN_CONN,
        maxconn=Config.DB_MAX_CONN,
        dsn=Config.DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,

        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    logger.info(f"✅ 数据库连接池已启动: {Config.DB_MIN_CONN} ~ {Config.DB_MAX_CONN}")
except Exception as e:
    logger.error(f"❌ 无法创建数据库连接池: {e}")
    raise


def is_connection_usable(conn) -> bool:
    """
    检查连接是否可用（防止 SSL 断连、EOF、服务端关闭等）
    """
    try:
        if conn.closed:
            logger.debug("连接已关闭")
            return False

        try:
            if conn.fileno() < 0:
                logger.debug("连接文件描述符无效")
                return False
        except (OSError, ValueError):
            logger.debug("连接文件描述符访问异常")
            return False

        status = conn.get_transaction_status()
        if status != 0:  # 0 = IDLE
            logger.debug(f"连接处于事务中 (状态: {status})，需要回滚")
            try:
                conn.rollback()
            except:
                return False

        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return True

    except (psycopg2.OperationalError, psycopg2.InterfaceError, OSError, EOFError) as e:
        logger.warning(f"连接不可用 (网络/操作错误): {repr(e)}")
        try:
            conn.close()
        except:
            pass
        return False

    except Exception as e:
        logger.warning(f"连接检测异常: {repr(e)}")
        try:
            conn.close()
        except:
            pass
        return False


def get_db():
    """
    获取数据库连接（优先从池中获取，失败则创建临时连接）
    """
    conn = None
    try:
        conn = db_pool.getconn()
        if conn is None:
            raise Exception("从连接池获取到 None 连接")

        # 检查连接是否可用
        if is_connection_usable(conn):
            conn.autocommit = False
            set_connection_context(conn, is_pooled=True)
            logger.debug(f"🔁 从连接池获取连接: {get_connection_id()}")
            return conn
        else:
            logger.warning(f"池中连接不可用，创建临时连接")
            try:
                db_pool.putconn(conn, close=True)
            except Exception as e:
                logger.warning(f"关闭无效池连接失败: {e}")
            conn = None
    except Exception as e:
        logger.warning(f"从连接池获取连接失败: {e}")
        if conn:
            try:
                db_pool.putconn(conn, close=True)
            except:
                pass
            conn = None

    # 创建临时连接
    try:
        conn = psycopg2.connect(
            Config.DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        conn.autocommit = False
        set_connection_context(conn, is_pooled=False)
        logger.info(f"🆕 创建临时连接: {get_connection_id()}")
        return conn
    except Exception as e:
        logger.error(f"无法创建临时数据库连接: {e}")
        raise


def close_db(conn):
    """
    安全关闭或归还连接
    """
    if not conn:
        _cleanup_tls()
        return

    cid = get_connection_id()

    if conn.closed:
        logger.debug(f"❌ 尝试关闭已关闭的连接: {cid}")
        _cleanup_tls()
        return

    try:
        status = conn.get_transaction_status()
        if status != 0:
            try:
                conn.rollback()
                logger.debug(f"🧹 强制回滚未完成事务: {cid}")
            except Exception as e:
                logger.warning(f"回滚失败 ({cid}): {e}")
                try:
                    conn.close()
                    _cleanup_tls()
                    return
                except:
                    pass

        try:
            cursor = conn.cursor()
            cursor.execute("RESET ALL")
            cursor.close()
        except Exception as e:
            logger.warning(f"RESET ALL 失败 ({cid}): {e}")

        if is_pooled_connection():
            try:
                db_pool.putconn(conn)
                logger.debug(f"✅ 池化连接已归还: {cid}")
            except Exception as e:
                logger.error(f"归还连接失败 ({cid}): {e}，正在关闭")
                try:
                    conn.close()
                except:
                    pass
        else:
            try:
                conn.close()
                logger.debug(f"🗑️ 临时连接已关闭: {cid}")
            except Exception as e:
                logger.error(f"关闭临时连接失败 ({cid}): {e}")

    except Exception as e:
        logger.error(f"关闭连接时出错 ({cid}): {e}")
        try:
            conn.close()
        except:
            pass
    finally:
        _cleanup_tls()


@contextmanager
def get_db_cursor(commit_on_success: bool = True):
    """
    数据库游标上下文管理器
    使用示例：
        with get_db_cursor() as cur:
            cur.execute("INSERT INTO ...")
    """
    conn = None
    cursor = None
    cid = "unknown"

    try:
        conn = get_db()
        cid = get_connection_id()
        cursor = conn.cursor()
        yield cursor

        if commit_on_success:
            try:
                conn.commit()
                logger.debug(f"✅ 事务已提交: {cid}")
            except Exception as e:
                try:
                    conn.rollback()
                    logger.debug(f"↩️ 提交失败，已回滚: {cid}")
                except:
                    pass
                raise
        else:
            try:
                conn.rollback()
                logger.debug(f"↩️ 事务已回滚（只读）: {cid}")
            except Exception as e:
                logger.warning(f"回滚失败 ({cid}): {e}")

    except Exception as e:
        logger.error(f"数据库操作失败: {e} (连接: {cid})")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        if cursor and not cursor.closed:
            try:
                cursor.close()
                logger.debug(f".Cursors 已关闭: {cid}")
            except Exception as e:
                logger.warning(f"关闭游标失败 ({cid}): {e}")
        if conn:
            close_db(conn)


# ==============================
# 关闭连接池（程序退出时）
# ==============================

import atexit

@atexit.register
def close_db_pool():
    global db_pool
    if db_pool is not None:
        try:
            db_pool.closeall()
            logger.info("🔗 数据库连接池已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭连接池时出错: {e}")
    else:
        logger.warning("⚠️ 无数据库连接池可关闭")