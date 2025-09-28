import uuid

def validate_uuid(uuid_string):
    """验证 UUID 格式"""
    try:
        uuid.UUID(uuid_string)
        return True
    except (ValueError, TypeError):
        return False

def validate_user_id(user_id):
    """验证用户 ID 格式"""
    if not validate_uuid(user_id):
        raise ValueError("Invalid UUID format")
    return user_id
