from flask import Blueprint, request, render_template, redirect, url_for, session, flash
from services.auth_service import authenticate_user, login_user, process_2fa_verification, process_backup_code_verification
from models.user import create_user, get_user_totp_info, update_last_login, update_user_totp, delete_user_totp, update_user_nickname
from utils.validators import validate_user_id, validate_uuid
from utils.security import hash_password, check_password, generate_totp_secret, get_totp_uri, make_qr_code_image, encrypt_data
from models.reputation import update_reputation
import psycopg2
import pyotp
import re
import secrets
import io
import base64
import os
import uuid

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        nickname = request.form['nickname'].strip()
        password = request.form['password']

        # 检查用户名格式
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_]{2,31}$', username) or len(username) < 6:
            flash('用户名必须为6-32个字符，只能包含字母、数字和下划线，且必须以字母或数字开头')
            return redirect(url_for('auth.register'))
        
        if not (1 <= len(nickname) <= 16):
            flash('昵称应当在1-16个字及之间')
            return redirect(url_for('auth.register'))
        if len(password) < 6:
            flash('密码必须至少为6个字符')
            return redirect(url_for('auth.register'))

        try:
            from models.database import get_db_cursor
            with get_db_cursor() as cursor:
                cursor.execute("SELECT id FROM taUsers WHERE username = %s", (username,))
                if cursor.fetchone():
                    flash('用户名已存在')
                    return redirect(url_for('auth.register'))

                password_hash = hash_password(password)
                user_id = str(uuid.uuid4())  # 生成新的 UUID
                cursor.execute("""
                    INSERT INTO taUsers (id, username, nickname, password_hash)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, username, nickname, password_hash))
                
                # 在同一个事务中更新声望
                update_reputation(
                    user_id=user_id,
                    change_type='initial',
                    amount=0,
                    description='账户注册',
                    cursor=cursor
                )

            flash('注册成功！请登录！')
            return redirect(url_for('auth.login'))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for('auth.register'))
        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Database error during registration: {e}")
            flash('出现错误，请重试')
            return redirect(url_for('auth.register'))

    elif request.method == 'GET':
        if session.get('user_id'):
            user_id = session.get('user_id')
            if validate_user_id(user_id):
                return redirect(url_for('main.dashboard'))
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']

        from models.database import get_db_cursor
        with get_db_cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT id, username, password_hash, is_2fa_enabled FROM taUsers WHERE username = %s",
                    (username,)
                )
                user = cursor.fetchone()

                if user and check_password(password, user['password_hash']):
                    # 验证 UUID
                    if not validate_uuid(user['id']):
                        flash('用户数据异常')
                        return redirect(url_for('auth.login'))
                    
                    # 更新最后登录时间
                    update_last_login(user['id'])

                    if user['is_2fa_enabled']:
                        session['pending_2fa_user_id'] = user['id']
                        session['2fa_stage'] = True
                        session.permanent = True
                        flash('请输入您的 2FA 验证码')
                        return redirect(url_for('auth.verify_2fa'))
                    else:
                        session['user_id'] = user['id']
                        session['username'] = user['username']
                        session.permanent = True
                        if 'pending_github_info' in session:
                            github_info = session.pop('pending_github_info')
                            from services.reputation_service import handle_github_login
                            handle_github_login(session['user_id'], github_info)
                            flash('GitHub 账号已自动绑定！')
                        flash('登录成功！')
                        return redirect(url_for('main.dashboard'))
                else:
                    flash('无效的用户名和密码')
                    return redirect(url_for('auth.login'))

            except psycopg2.Error as e:
                from flask import current_app
                current_app.logger.error(f"Login error: {e}")
                flash('登录时出现错误')
                return redirect(url_for('auth.login'))

    elif request.method == 'GET':
        if session.get('user_id'):
            user_id = session.get('user_id')
            if validate_uuid(user_id):
                return redirect(url_for('main.dashboard'))

    return render_template('login.html')

@auth_bp.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    if 'pending_2fa_user_id' not in session:
        flash('非法访问')
        return redirect(url_for('auth.login'))

    user_id = session['pending_2fa_user_id']
    if not validate_uuid(user_id):
        session.clear()
        flash('会话异常')
        return redirect(url_for('auth.login'))

    if request.method == 'GET':
        return render_template('verify_2fa.html')

    try:
        from models.database import get_db_cursor
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT t.totp_secret_encrypted, t.backup_codes_salt, t.backup_codes_encrypted
                FROM taUserTOTP t
                WHERE t.user_id = %s
            """, (user_id,))
            row = cursor.fetchone()
            if not row:
                flash('未配置 2FA，请联系管理员')
                return redirect(url_for('auth.login'))

            from utils.security import decrypt_data
            secret = decrypt_data(row['totp_secret_encrypted'], row['backup_codes_salt'])
            totp = pyotp.TOTP(secret)

            token = request.form['token'].strip()

            if totp.verify(token):
                cursor.execute("SELECT username FROM taUsers WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                session['user_id'] = user_id
                session['username'] = user['username']
                session.pop('pending_2fa_user_id', None)
                session.pop('2fa_stage', None)
                cursor.execute("UPDATE taUserTOTP SET last_used_at = NOW() WHERE user_id = %s", (user_id,))
                
                # 检查是否是首次2FA验证
                cursor.execute("""
                    SELECT COUNT(*) as usage_count 
                    FROM taUsersReputationLogs 
                    WHERE user_id = %s AND change_type = 'first_2fa_verification'
                """, (user_id,))
                log_entry = cursor.fetchone()
                
                # 如果没有记录，说明是首次验证，给予声望奖励
                if log_entry and log_entry['usage_count'] == 0:
                    update_reputation(
                        user_id=user_id,
                        change_type='first_2fa_verification',
                        amount=10,
                        description="首次成功完成2FA验证"
                    )
                
                if 'pending_github_info' in session:
                    github_info = session.pop('pending_github_info')
                    from services.reputation_service import handle_github_login
                    handle_github_login(session['user_id'], github_info)
                    flash('GitHub 账号已自动绑定！')
                flash('2FA 验证成功！')
                return redirect(url_for('main.dashboard'))

            # 尝试备份码
            if row['backup_codes_encrypted']:
                try:
                    backup_codes = decrypt_data(row['backup_codes_encrypted'], row['backup_codes_salt'])
                    codes = set(backup_codes.split(","))
                    if token in codes:
                        codes.remove(token)
                        new_encrypted, _ = encrypt_data(",".join(codes), row['backup_codes_salt'])
                        cursor.execute(
                            "UPDATE taUserTOTP SET backup_codes_encrypted = %s, last_used_at = NOW() WHERE user_id = %s",
                            (new_encrypted, user_id)
                        )
                        cursor.execute("SELECT username FROM taUsers WHERE id = %s", (user_id,))
                        user = cursor.fetchone()
                        session['user_id'] = user_id
                        session['username'] = user['username']
                        session.pop('pending_2fa_user_id', None)
                        session.pop('2fa_stage', None)
                        
                        # 检查是否是首次2FA验证（备份码方式）
                        cursor.execute("""
                            SELECT COUNT(*) as usage_count 
                            FROM taUsersReputationLogs 
                            WHERE user_id = %s AND change_type = 'first_2fa_verification'
                        """, (user_id,))
                        log_entry = cursor.fetchone()
                        
                        if log_entry and log_entry['usage_count'] == 0:
                            update_reputation(
                                user_id=user_id,
                                change_type='first_2fa_verification',
                                amount=10,
                                description="首次成功完成2FA验证（使用备份码）"
                            )
                        
                        if 'pending_github_info' in session:
                            github_info = session.pop('pending_github_info')
                            from services.reputation_service import handle_github_login
                            handle_github_login(session['user_id'], github_info)
                            flash('GitHub 账号已自动绑定！')
                        flash('备份码验证成功！')
                        return redirect(url_for('main.dashboard'))
                except Exception as e:
                    from flask import current_app
                    current_app.logger.warning(f"Backup code decryption failed: {e}")

            flash('无效的验证码或已过期')
            return redirect(url_for('auth.verify_2fa'))

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"2FA verification error: {e}")
        flash('验证失败')
        return redirect(url_for('auth.verify_2fa'))

@auth_bp.route('/setup-2fa', methods=['GET', 'POST'])
def setup_totp():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    if not validate_uuid(user_id):
        session.clear()
        flash('会话异常')
        return redirect(url_for('auth.login'))
    
    try:
        from models.database import get_db_cursor
        with get_db_cursor() as cursor:
            if request.method == 'POST':
                token = request.form['token'].strip()
                want_enable = request.form.get('action') == 'enable'

                if not want_enable:
                    delete_user_totp(user_id)
                    flash('2FA 已关闭')
                    return redirect(url_for('main.dashboard'))

                secret = session.get('temp_totp_secret')
                if not secret:
                    flash('请先刷新页面重新开始')
                    return redirect(url_for('auth.setup_totp'))

                totp = pyotp.TOTP(secret)
                if not totp.verify(token, valid_window=1):
                    flash('验证码错误或已过期')
                    return redirect(url_for('auth.setup_totp'))

                salt = os.urandom(16).hex()
                encrypted_secret, _ = encrypt_data(secret, salt)

                backup_codes = [secrets.token_urlsafe(16) for _ in range(10)]
                backup_codes_str = ",".join(backup_codes)
                encrypted_backup, _ = encrypt_data(backup_codes_str, salt)

                update_user_totp(user_id, encrypted_secret, encrypted_backup, salt)

                session['generated_backup_codes'] = backup_codes
                session.pop('temp_totp_secret', None)
                return redirect(url_for('auth.show_backup_codes'))

            secret = generate_totp_secret()
            session['temp_totp_secret'] = secret

            cursor.execute("SELECT username FROM taUsers WHERE id = %s", (user_id,))
            username = cursor.fetchone()['username']

            uri = get_totp_uri(username, secret)
            qr_image = make_qr_code_image(uri)

            return render_template('setup_2fa.html', qr_image=qr_image, secret=secret)

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Setup 2FA error: {e}")
        flash('操作失败')
        return redirect(url_for('main.dashboard'))

@auth_bp.route('/backup-codes')
def show_backup_codes():
    if 'generated_backup_codes' not in session:
        return redirect(url_for('main.dashboard'))
    codes = session.pop('generated_backup_codes')
    return render_template('backup_codes.html', codes=codes)

@auth_bp.route('/use-backup-codes', methods=['GET', 'POST'])
def use_backup_codes():
    if 'pending_2fa_user_id' not in session:
        flash('非法访问')
        return redirect(url_for('auth.login'))

    user_id = session['pending_2fa_user_id']
    if not validate_uuid(user_id):
        session.clear()
        flash('会话异常')
        return redirect(url_for('auth.login'))

    if request.method == 'GET':
        return render_template('use_backup_codes.html')

    try:
        from models.database import get_db_cursor
        from utils.security import decrypt_data
        with get_db_cursor() as cursor:
            if request.method == 'POST':
                token = request.form['token'].strip()
                cursor.execute("""
                    SELECT backup_codes_encrypted, backup_codes_salt
                    FROM taUserTOTP
                    WHERE user_id = %s
                """, (user_id,))
                row = cursor.fetchone()
                if not row:
                    flash('未配置 2FA，请联系管理员')
                    return redirect(url_for('auth.login'))

                try:
                    decrypted_codes = decrypt_data(row['backup_codes_encrypted'], row['backup_codes_salt'])
                    backup_codes = set(decrypted_codes.split(","))
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"Failed to decrypt backup codes: {e}")
                    flash('内部错误，请联系管理员')
                    return redirect(url_for('auth.login'))

                if token in backup_codes:
                    backup_codes.remove(token)
                    updated_codes_str = ",".join(backup_codes)
                    new_encrypted, _ = encrypt_data(updated_codes_str, row['backup_codes_salt'])
                    cursor.execute("""
                        UPDATE taUserTOTP
                        SET backup_codes_encrypted = %s, last_used_at = NOW()
                        WHERE user_id = %s
                    """, (new_encrypted, user_id))
                    cursor.execute("SELECT username FROM taUsers WHERE id = %s", (user_id,))
                    user = cursor.fetchone()
                    session['user_id'] = user_id
                    session['username'] = user['username']
                    session.pop('pending_2fa_user_id', None)
                    session.pop('2fa_stage', None)
                    if 'pending_github_info' in session:
                        github_info = session.pop('pending_github_info')
                        from services.reputation_service import handle_github_login
                        handle_github_login(session['user_id'], github_info)
                        flash('GitHub 账号已自动绑定！')
                    flash('备份码验证成功！')
                    return redirect(url_for('main.dashboard'))
                else:
                    flash('无效的备份码')
                    return redirect(url_for('auth.use_backup_codes'))

            return render_template('use_backup_codes.html')

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Backup code verification error: {e}")
        flash('验证失败，请重试')
        return redirect(url_for('auth.use_backup_codes'))

@auth_bp.route('/auth/update-nickname', methods=['POST'])
def auth_update_nickname():
    if 'user_id' not in session:
        flash('未登录', 'error')
        return redirect(url_for('main.login'))

    user_id = session['user_id']
    if not validate_uuid(user_id):
        flash('会话异常', 'error')
        return redirect(url_for('main.index'))

    new_nickname = request.form.get('nickname', '').strip()

    if not (1 <= len(new_nickname) <= 16):
        flash('昵称长度必须为1-16个字符', 'error')
        return redirect(request.referrer or url_for('main.index'))

    try:
        update_user_nickname(user_id=user_id, new_nickname=new_nickname)
        flash('昵称更新成功', 'success')
        return redirect(request.referrer or url_for('main.dashboard'))
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"更新昵称失败: {e}")
        flash('服务器错误', 'error')
        return redirect(request.referrer or url_for('main.dashboard'))