TeeAlloy
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
========
开源Teeworlds账号系统带网页注册的实现，使用2FA加强安全性。

# 使用

请在生产环境中设置强随机密钥，**切勿依赖默认值**。

生成SECRET_KEY
```python
python -c "import os; print(os.urandom(24).hex())"
```

生成FERNET_KEY
```python
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
然后将生成出来的设置为环境变量。

配置DATABASE_URL
```
postgresql://<user>:<password>@<host>:<port>/<dbname>
```

# 配置
| 键 | 默认 |
| ---- | ---- |
| DB_MIN_CONN | 2 |
| DB_MAX_CONN | 10 |
| DATABASE_URL | postgresql://teealloytest:test@localhost:5432/teealloydb |

# API
```
POST /api/auth/verify-game-token
```
请求头:
```
Content-Type: application/json
X-API-Key: <API-Key>
X-Server-Address: <API-Key在后台面板对应的地址>
```
请求体:
```json
{
  "game_token": "string",
  "nickname": "string"
}
```
成功响应:
```json
{
  "success": true,
  "user": {
    "user_id": "UUID",
    "reputation": "Int",
    "is_banned": "Boolean",
    "created_at": "Timestamp"
  }
}
```

错误响应:
```json
400 Bad Request
{
  "success": false,
  "error": "Missing or invalid game_token"
}

400 Bad Request
{
  "success": false,
  "error": "Missing or invalid nickname"
}

401 Unauthorized
{
  "success": false,
  "error": "Invalid or expired game_token"
}

404 Not Found
{
  "success": false,
  "error": "User not found"
}

500 Internal Server Error
{
  "success": false,
  "error": "User not found"
}

```