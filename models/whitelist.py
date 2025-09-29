# models/whitelist.py
from models.database import get_db_cursor
from utils import hash_api_key
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def add_whitelist_server(server_address: str, api_key_hash: str) -> bool:
    """
    添加一个白名单服务器记录
    :param server_address: 服务器地址（IP 或域名），如 '192.168.1.100' 或 'game.mygame.com'
    :param api_key_hash: API 密钥 Hash
    :return: 是否新增成功（False 可能是已存在）
    """
    if not server_address or not api_key_hash:
        raise ValueError("server_address and api_key_hash are required")

    try:
        with get_db_cursor(commit_on_success=True) as cursor:
            cursor.execute("""
                INSERT INTO taWhiteListServers (server_address, api_key_hash)
                VALUES (%s, %s)
                ON CONFLICT (server_address, api_key_hash) DO NOTHING
            """, (server_address, api_key_hash))

            if cursor.rowcount > 0:
                logger.info(f"Whitelist server added: {server_address}")
                return True
            else:
                logger.warning(f"Whitelist entry already exists: {server_address}")
                return False
    except Exception as e:
        logger.error(f"Failed to add whitelist server {server_address}: {e}")
        raise


def remove_whitelist_server(server_address: str, api_key: str) -> bool:
    """
    移除一个白名单记录
    :param server_address: 服务器地址
    :param api_key: 要删除的 API 密钥Hash
    :return: 是否删除成功
    """
    api_key_hash = api_key # 不需要再hash

    try:
        with get_db_cursor(commit_on_success=True) as cursor:
            cursor.execute("""
                DELETE FROM taWhiteListServers
                WHERE server_address = %s AND api_key_hash = %s
            """, (server_address, api_key_hash))
            deleted = cursor.rowcount > 0

            if deleted:
                logger.info(f"Whitelist server removed: {server_address}")
            else:
                logger.warning(f"No matching record to delete for {server_address}")

            return deleted
    except Exception as e:
        logger.error(f"Failed to remove whitelist server {server_address}: {e}")
        raise


def get_whitelist_by_address(server_address: str) -> List[Dict]:
    """
    获取某个 server_address 的所有白名单记录
    :param server_address: 服务器地址
    :return: 列表，包含 api_key_hash 和 created_at
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT server_address, api_key_hash, created_at
                FROM taWhiteListServers
                WHERE server_address = %s
                ORDER BY created_at DESC
            """, (server_address,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error querying whitelist for {server_address}: {e}")
        raise


def get_all_whitelist_servers() -> List[Dict]:
    """
    获取所有白名单服务器记录（用于管理界面）
    :return: 所有记录列表
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT server_address, api_key_hash, created_at
                FROM taWhiteListServers
                ORDER BY server_address, created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching all whitelist servers: {e}")
        raise


def is_server_authorized(server_address: str, api_key: str) -> bool:
    """
    验证服务器是否在白名单中
    :param server_address: 客户端声明的地址（建议强制由 header 提供）
    :param api_key: 明文 API 密钥
    :return: 是否授权通过
    """
    if not server_address or not api_key:
        return False

    try:
        api_key_hash = hash_api_key(api_key)

        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM taWhiteListServers
                WHERE server_address = %s AND api_key_hash = %s
                LIMIT 1
            """, (server_address, api_key_hash))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Authorization check failed for {server_address}: {e}")
        return False
