# utils/github.py

import requests
import os
from typing import Dict, Optional

# GitHub API endpoints
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

# Teeworlds repo for contributor check
TEEWORLDS_REPO = "https://api.github.com/repos/teeworlds/teeworlds/contributors?per_page=200"

def get_github_login_url(redirect_uri: str, state: str) -> str:
    """
    生成 GitHub OAuth 登录链接
    :param redirect_uri: 回调地址（必须与注册一致）
    :param state: 随机字符串，防 CSRF
    :return: 授权 URL
    """
    client_id = os.environ.get("GITHUB_CLIENT_ID")
    if not client_id:
        raise RuntimeError("GITHUB_CLIENT_ID 环境变量未设置")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "read:user",  # 只需要读取用户基本信息
        "state": state
    }
    from urllib.parse import urlencode
    query = urlencode(params)
    return f"{GITHUB_AUTH_URL}?{query}"


def exchange_code_for_token(code: str, redirect_uri: str) -> Optional[str]:
    """
    使用授权码换取 access_token
    :param code: GitHub 返回的 code
    :param redirect_uri: 必须与请求时一致
    :return: access_token 或 None
    """
    client_id = os.environ.get("GITHUB_CLIENT_ID")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError("GITHUB_CLIENT_ID 或 GITHUB_CLIENT_SECRET 未设置")

    headers = {"Accept": "application/json"}
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri
    }

    resp = requests.post(GITHUB_TOKEN_URL, data=data, headers=headers)
    if resp.status_code != 200:
        return None

    token_data = resp.json()
    return token_data.get("access_token")


def get_github_user_info(access_token: str) -> Optional[Dict]:
    """
    获取 GitHub 用户信息
    :param access_token: 有效的 access token
    :return: 包含 id, login, name, avatar_url 等的字典
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    resp = requests.get(GITHUB_USER_URL, headers=headers)
    if resp.status_code != 200:
        return None

    user_data = resp.json()
    return {
        "id": user_data["id"],
        "login": user_data["login"],
        "name": user_data.get("name"),
        "email": user_data.get("email"),
        "avatar_url": user_data["avatar_url"],
        "profile_url": user_data["html_url"]
    }


def is_teeworlds_contributor(github_login: str) -> bool:
    """
    检查是否为 Teeworlds 项目贡献者（最多前200人）
    """
    try:
        resp = requests.get(TEEWORLDS_REPO, timeout=10)
        if resp.status_code == 200:
            contributors = [item['login'] for item in resp.json()]
            return github_login in contributors
    except Exception as e:
        print(f"检查贡献者失败: {e}")
    return False