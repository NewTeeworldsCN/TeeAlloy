from models.reputation import update_reputation, on_github_login, endorse_user, on_user_ban, make_full_reputation
from utils.validators import validate_user_id

def handle_github_login(user_id, github_info):
    """处理GitHub登录"""
    on_github_login(user_id, github_info)

def handle_user_endorsement(endorser_id, endorsee_id):
    """处理用户验证"""
    validate_user_id(endorser_id)
    validate_user_id(endorsee_id)
    return endorse_user(endorser_id, endorsee_id)

def handle_user_ban(banned_user_id, cursor):
    """处理用户封禁"""
    validate_user_id(banned_user_id)
    on_user_ban(banned_user_id, cursor=cursor)

