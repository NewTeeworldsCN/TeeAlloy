# scripts/add_whitelist_server.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import get_db_cursor
from models.whitelist import hash_api_key
import sys

if len(sys.argv) != 3:
    print("Usage: python add_whitelist_server.py <server_address> <api_key>")
    sys.exit(1)

server_addr = sys.argv[1]
api_key = sys.argv[2]
api_key_hash = hash_api_key(api_key)

with get_db_cursor(commit_on_success=True) as cursor:
    cursor.execute("""
        INSERT INTO taWhiteListServers (server_address, api_key_hash)
        VALUES (%s, %s)
        ON CONFLICT (server_address, api_key_hash) DO NOTHING
    """, (server_addr, api_key_hash))

print(f"✅ Server '{server_addr}' added to whitelist.")
