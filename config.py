import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY or SECRET_KEY == 'your-secret-key-here-change-it-in-production':
        raise ValueError("SECRET_KEY environment variable must be set")
    
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://teealloytest:test@localhost:5432/teealloydb")
    DB_MIN_CONN = int(os.environ.get("DB_MIN_CONN", 2))
    DB_MAX_CONN = int(os.environ.get("DB_MAX_CONN", 10))
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
