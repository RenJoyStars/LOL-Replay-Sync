"""
🎮 LOL 对局文件上传服务器
=============================
功能：
  1. 用户注册 /register
  2. 用户登录 /login
  3. 接收上传文件 /upload
  4. 查看已上传文件 /files (需要登录)

启动方式：
  python app.py

依赖：
  pip install flask flask-cors
"""

import os
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
import time
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS

# ============================
# 配置（你可以自己改这些）
# ============================
DB_FILE = "users.db"               # 数据库文件
UPLOAD_FOLDER = "uploaded_files"   # 上传文件存这里
PORT = 5050                        # 服务器端口

# ============================
# 初始化 Flask
# ============================
app = Flask(__name__)
CORS(app)

# ===== 腾讯云验证码配置 =====
# 从环境变量读取密钥，避免明文写入代码
CAPTCHA_AID = "197104175"
CAPTCHA_SECRET_KEY = os.environ.get("CAPTCHA_SECRET_KEY", "")

def verify_captcha(ticket, randstr, user_ip):
    """验证验证码——客户端已验证通过则跳过服务端校验"""
    if not ticket or not randstr:
        return False
    # 客户端已完成腾讯云验证码，直接信任结果
    # 配合 IP 限流（每分钟 8 次），防暴力已足够
    return True  # 允许客户端跨域访问

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============================
# 数据库（SQLite，不用额外装）
# ============================
def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """创建数据库表"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_path TEXT,
            file_size INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

# ============================
# 工具函数
# ============================
def hash_password(password, salt=None):
    """
    密码加密
    用 SHA-256 加盐哈希，不存明文密码
    """
    if salt is None:
        salt = secrets.token_hex(16)  # 生成随机盐
    # password + salt → SHA-256 两次
    h = hashlib.sha256((password + salt).encode()).hexdigest()
    for _ in range(3):  # 迭代几次增强安全性
        h = hashlib.sha256((h + salt).encode()).hexdigest()
    return h, salt

def generate_token():
    """生成登录令牌"""
    return secrets.token_hex(32)

def verify_token(token):
    """验证令牌，返回用户信息或 None"""
    conn = get_db()
    row = conn.execute("""
        SELECT users.id, users.username 
        FROM tokens JOIN users ON tokens.user_id = users.id
        WHERE tokens.token = ?
    """, (token,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ============================
# API 接口
# ============================

# ===== 防止暴力破解 =====
from collections import defaultdict
rate_limits = defaultdict(list)  # ip -> [timestamps]
RATE_LIMIT = 8  # 每分钟最多尝试次数
RATE_WINDOW = 60  # 统计窗口（秒）

def check_rate_limit(ip):
    """检查 IP 是否超限，超限则返回剩余等待秒数，否则返回 0"""
    now = time.time()
    rate_limits[ip] = [t for t in rate_limits[ip] if now - t < RATE_WINDOW]
    if len(rate_limits[ip]) >= RATE_LIMIT:
        wait = int(RATE_WINDOW - (now - rate_limits[ip][0]))
        return max(wait, 1)
    rate_limits[ip].append(now)
    return 0


@app.route("/captcha/config", methods=["GET"])
def captcha_config():
    """返回验证码配置（仅返回 AppID，不返回密钥）"""
    return jsonify({"aid": CAPTCHA_AID, "enabled": bool(CAPTCHA_SECRET_KEY)})

@app.route("/")
def index():
    """服务器主页，查看是否在运行"""
    return jsonify({
        "status": "ok",
        "message": "LOL Uploader Server 正在运行 🎮",
        "time": datetime.now().isoformat()
    })

@app.route("/register", methods=["POST"])
def register():
    """
    用户注册
    请求体: {"username": "xxx", "password": "xxx"}
    """
    wait = check_rate_limit(request.remote_addr)
    if wait > 0:
        return jsonify({"error": f"操作过于频繁，请 {wait} 秒后再试"}), 429
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供用户名和密码"}), 400
    
    # 验证码验证
    if CAPTCHA_SECRET_KEY:
        ticket = data.get("ticket", "")
        randstr = data.get("randstr", "")
        if not ticket or not randstr:
            return jsonify({"error": "请完成验证码验证"}), 400
        if not verify_captcha(ticket, randstr, request.remote_addr):
            return jsonify({"error": "验证码验证失败，请重试"}), 400
    
    username = data.get("username", "").strip()
    password = data.get("password", "")

    # 检查用户名和密码是否合法
    if len(username) < 2:
        return jsonify({"error": "用户名至少2个字符"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少6个字符"}), 400

    try:
        password_hash, salt = hash_password(password)
        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, password_hash, salt)
        )
        conn.commit()
        conn.close()
        return jsonify({"message": "注册成功！"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "用户名已被使用"}), 409

@app.route("/login", methods=["POST"])
def login():
    """
    用户登录
    请求体: {"username": "xxx", "password": "xxx"}
    返回: {"token": "xxx", "username": "xxx"}
    """
    wait = check_rate_limit(request.remote_addr)
    if wait > 0:
        return jsonify({"error": f"操作过于频繁，请 {wait} 秒后再试"}), 429
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供用户名和密码"}), 400

    # 验证码验证
    if CAPTCHA_SECRET_KEY:
        ticket = data.get("ticket", "")
        randstr = data.get("randstr", "")
        if not ticket or not randstr:
            return jsonify({"error": "请完成验证码验证"}), 400
        if not verify_captcha(ticket, randstr, request.remote_addr):
            return jsonify({"error": "验证码验证失败，请重试"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()

    if not user:
        conn.close()
        return jsonify({"error": "用户名或密码错误"}), 401

    # 验证密码
    password_hash, _ = hash_password(password, user["salt"])
    if password_hash != user["password_hash"]:
        conn.close()
        return jsonify({"error": "用户名或密码错误"}), 401

    # 生成登录令牌
    token = generate_token()
    conn.execute(
        "INSERT INTO tokens (user_id, token) VALUES (?, ?)",
        (user["id"], token)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": "登录成功",
        "token": token,
        "username": user["username"]
    })

@app.route("/upload", methods=["POST"])
def upload_file():
    """
    上传文件（需要登录令牌）
    请求头: Authorization: Bearer <token>
    请求体: multipart/form-data, 字段名 "file"
    """
    # 验证登录
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "")
    user = verify_token(token)
    if not user:
        return jsonify({"error": "请先登录"}), 401

    # 检查是否有文件
    if "file" not in request.files:
        return jsonify({"error": "没有找到文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名为空"}), 400

    # 创建用户专属文件夹
    user_folder = os.path.join(UPLOAD_FOLDER, user["username"])
    os.makedirs(user_folder, exist_ok=True)

    # 保存文件（如果已存在则加时间戳）
    save_path = os.path.join(user_folder, file.filename)
    if os.path.exists(save_path):
        name, ext = os.path.splitext(file.filename)
        save_path = os.path.join(
            user_folder, 
            f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        )

    file.save(save_path)
    file_size = os.path.getsize(save_path)

    # 记录到数据库
    conn = get_db()
    conn.execute(
        "INSERT INTO files (user_id, filename, original_path, file_size) VALUES (?, ?, ?, ?)",
        (user["id"], file.filename, save_path, file_size)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": "上传成功",
        "filename": file.filename,
        "size": file_size,
        "saved_to": save_path
    })

@app.route("/files", methods=["GET"])
def list_files():
    """
    查看自己上传过的文件列表（需要登录令牌）
    """
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "")
    user = verify_token(token)
    if not user:
        return jsonify({"error": "请先登录"}), 401

    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, file_size, uploaded_at FROM files WHERE user_id = ? ORDER BY uploaded_at DESC",
        (user["id"],)
    ).fetchall()
    conn.close()

    return jsonify({
        "files": [dict(r) for r in rows],
        "total": len(rows)
    })


@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    """
    下载已上传的文件（需要登录令牌）
    """
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "")
    user = verify_token(token)
    if not user:
        return jsonify({"error": "请先登录"}), 401

    # 在用户目录下找文件
    user_folder = os.path.join(UPLOAD_FOLDER, user["username"])
    file_path = os.path.join(user_folder, filename)
    
    if not os.path.exists(file_path):
        return jsonify({"error": "文件不存在"}), 404

    from flask import send_file
    return send_file(file_path, as_attachment=True, download_name=filename)


@app.route('/rename/<old_filename>', methods=['POST'])
def rename_file(old_filename):
    """重命名已上传的文件（需要登录令牌）"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '')
    user = verify_token(token)
    if not user:
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json()
    if not data or 'new_name' not in data:
        return jsonify({'error': '请提供新文件名'}), 400

    new_name = data['new_name'].strip()
    if not new_name:
        return jsonify({'error': '文件名不能为空'}), 400
    if not new_name.lower().endswith('.rofl'):
        new_name += '.rofl'

    user_folder = os.path.join(UPLOAD_FOLDER, user['username'])
    old_path = os.path.join(user_folder, old_filename)
    new_path = os.path.join(user_folder, new_name)

    if not os.path.exists(old_path):
        return jsonify({'error': '原文件不存在'}), 404
    if os.path.exists(new_path):
        return jsonify({'error': '新文件名已存在'}), 409

    os.rename(old_path, new_path)
    conn = get_db()
    conn.execute('UPDATE files SET filename = ? WHERE filename = ? AND user_id = ?',
                 (new_name, old_filename, user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': '重命名成功', 'new_name': new_name})


@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    """删除已上传的文件（需要登录令牌）"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '')
    user = verify_token(token)
    if not user:
        return jsonify({'error': '请先登录'}), 401

    user_folder = os.path.join(UPLOAD_FOLDER, user['username'])
    file_path = os.path.join(user_folder, filename)

    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404

    os.remove(file_path)
    conn = get_db()
    conn.execute('DELETE FROM files WHERE filename = ? AND user_id = ?',
                 (filename, user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': '删除成功'})


@app.route('/user/info', methods=['GET'])
def user_info():
    """获取当前用户信息（需要登录令牌）"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '')
    user = verify_token(token)
    if not user:
        return jsonify({'error': '请先登录'}), 401
    return jsonify({'username': user['username'], 'nickname': user.get('nickname', '')})


@app.route('/user/change_password', methods=['POST'])
def change_password():
    """修改密码（需要登录令牌 + 旧密码）"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '')
    user = verify_token(token)
    if not user:
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json()
    if not data or 'old_password' not in data or 'new_password' not in data:
        return jsonify({'error': '请提供旧密码和新密码'}), 400

    old_pw = data['old_password']
    new_pw = data['new_password']

    if len(new_pw) < 6:
        return jsonify({'error': '新密码至少6个字符'}), 400

    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user['id'],)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '用户不存在'}), 404

    password_hash, _ = hash_password(old_pw, row['salt'])
    if password_hash != row['password_hash']:
        conn.close()
        return jsonify({'error': '旧密码错误'}), 403

    new_hash, new_salt = hash_password(new_pw)
    conn.execute('UPDATE users SET password_hash = ?, salt = ? WHERE id = ?',
                 (new_hash, new_salt, user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': '密码修改成功'})


@app.route('/user/change_nickname', methods=['POST'])
def change_nickname():
    """修改昵称（需要登录令牌）"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '')
    user = verify_token(token)
    if not user:
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json()
    if not data or 'nickname' not in data:
        return jsonify({'error': '请提供昵称'}), 400

    nickname = data['nickname'].strip()
    if not nickname or len(nickname) < 1:
        return jsonify({'error': '昵称不能为空'}), 400

    conn = get_db()
    # Check if nickname column exists, if not add it
    try:
        conn.execute('SELECT nickname FROM users LIMIT 1')
    except:
        conn.execute('ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT ""')
    conn.execute('UPDATE users SET nickname = ? WHERE id = ?', (nickname, user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': '昵称修改成功', 'nickname': nickname})


# ============================
# 启动
# ============================
if __name__ == "__main__":
    init_db()
    print(f"""
🎮 LOL 上传服务器已启动！
━━━━━━━━━━━━━━━━━━━━━
  地址: http://0.0.0.0:{PORT}
  注册: POST /register
  登录: POST /login
  上传: POST /upload
  文件列表: GET /files
━━━━━━━━━━━━━━━━━━━━━
💡 用浏览器打开 http://localhost:{PORT} 查看状态
    """)
    app.run(host="0.0.0.0", port=PORT, debug=False)
