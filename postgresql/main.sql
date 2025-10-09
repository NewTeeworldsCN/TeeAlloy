-- 用户主表
CREATE TABLE taUsers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(32) UNIQUE NOT NULL CHECK (
        username ~ '^[a-zA-Z0-9][a-zA-Z0-9_]{5,31}$'
    ),
    nickname VARCHAR(65) NOT NULL,
    is_2fa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- TOTP 2FA 记录表
CREATE TABLE taUserTOTP (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES taUsers(id) ON DELETE CASCADE,
    totp_secret_encrypted BYTEA,
    backup_codes_encrypted BYTEA,
    backup_codes_salt CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    CONSTRAINT uk_tausertotp_user_id UNIQUE (user_id)
);


-- 游戏会话/令牌表
CREATE TABLE taUserGame (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES taUsers(id) ON DELETE CASCADE,
    game_token BYTEA NOT NULL,
    salt CHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    CONSTRAINT uk_tausergame_user_id UNIQUE (user_id)
);

-- 用户声望评分表
CREATE TABLE taUsersReputation (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES taUsers(id) ON DELETE CASCADE,
    score INTEGER NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
    is_contributor BOOLEAN NOT NULL DEFAULT FALSE,
    has_github_login BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- GitHub 登录绑定表
CREATE TABLE taUserGitHub (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES taUsers(id) ON DELETE CASCADE,
    github_id BIGINT NOT NULL UNIQUE,
    github_login TEXT NOT NULL,
    avatar_url TEXT,
    is_teeworlds_contributor BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 信用背书关系表
CREATE TABLE taCreditEndorsements (
    id SERIAL PRIMARY KEY,
    endorsee_id UUID NOT NULL REFERENCES taUsers(id) ON DELETE CASCADE,
    endorser_id UUID NOT NULL REFERENCES taUsers(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    invalidated_at TIMESTAMPTZ,

    CONSTRAINT uk_endorsement_pair UNIQUE (endorsee_id, endorser_id),
    CONSTRAINT chk_not_self_endorse CHECK (endorsee_id != endorser_id)
);

-- 声望变更日志表
CREATE TABLE taUsersReputationLogs (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES taUsers(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL CHECK (
        change_type IN (
            'initial',
            'github_login',
            'teeworlds_contributor',
            'endorsed_by_user',
            'endorsement_revoked',
            'penalty',
            'manual_adjust',
            'first_2fa_verification',
            'unbanned_by_admin'
        )
    ),
    change_amount INTEGER NOT NULL,
    old_score INTEGER NOT NULL CHECK (old_score BETWEEN 0 AND 100),
    new_score INTEGER NOT NULL CHECK (new_score BETWEEN 0 AND 100),
    related_user_id UUID REFERENCES taUsers(id),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 待删除用户记录表
CREATE TABLE taPendingDeletion (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES taUsers(id) ON DELETE CASCADE,
    marked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deletion_due TIMESTAMPTZ NOT NULL,
    is_processed BOOLEAN NOT NULL DEFAULT FALSE
);

-- 白名单服务器表
CREATE TABLE taWhiteListServers (
    id SERIAL PRIMARY KEY,
    server_address VARCHAR(45) NOT NULL,
    api_key_hash CHAR(64) NOT NULL,      -- SHA-256 Hex 编码
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uk_server_apikey UNIQUE (server_address, api_key_hash)
);

-- 自动更新 updated_at 的触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 触发器：自动更新 updated_at 字段
CREATE TRIGGER trg_update_tausers_updated_at
    BEFORE UPDATE ON taUsers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_update_tausertotp_updated_at
    BEFORE UPDATE ON taUserTOTP
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_update_tausergame_updated_at
    BEFORE UPDATE ON taUserGame
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_reputation_user ON taUsersReputationLogs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usertoken_user ON taUserGame(user_id);
CREATE INDEX IF NOT EXISTS idx_users_nickname ON taUsers(nickname);