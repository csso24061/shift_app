import os
import sqlite3
from flask import Flask, jsonify, request, send_file

app = Flask(__name__)
DB_FILE = "shifts.db"

# データベースの初期化
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # シフトテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            break_time INTEGER DEFAULT 0,
            status TEXT DEFAULT 'applied'
        )
    """)
    # 設定テーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # デフォルト設定値の投入
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('deadlineDate', '毎月20日')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('closingDate', '毎月末日')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('paymentDate', '翌月15日')")
    
    conn.commit()
    conn.close()

init_db()

# ユーザーデータ（簡易版）
USERS = {
    "staff01": {"username": "staff01", "password": "password123", "name": "テストスタッフ", "role": "staff"},
    "admin01": {"username": "admin01", "password": "adminpassword", "name": "管理者ユーザー", "role": "manager"}
}

# ==========================================
# 1. ログイン画面を表示するルート (最重要)
# ==========================================
@app.route('/')
def index():
    # 同じフォルダにある index.html をブラウザに返します
    return send_file('index.html')

# ==========================================
# 2. APIルート
# ==========================================

# ログインAPI
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    user_id = data.get('userId')
    password = data.get('password')

    user = USERS.get(user_id)
    if user and user['password'] == password:
        return jsonify({
            "status": "success",
            "user": {
                "username": user["username"],
                "name": user["name"],
                "role": user["role"]
            }
        })
    return jsonify({"status": "error", "message": "ユーザーIDまたはパスワードが違います。"}), 401

# シフト一覧取得API
@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, name, date, start_time, end_time, break_time, status FROM shifts ORDER BY date DESC")
    rows = cursor.fetchall()
    conn.close()

    shifts = []
    for row in rows:
        # 労働時間計算
        try:
            sh, sm = map(int, row[4].split(':'))
            eh, em = map(int, row[5].split(':'))
            total_min = (eh * 60 + em) - (sh * 60 + sm) - int(row[6])
            total_hours = round(max(0, total_min / 60.0), 1)
        except Exception:
            total_hours = 0.0

        shifts.append({
            "id": row[0],
            "username": row[1],
            "name": row[2],
            "date": row[3],
            "startTime": row[4],
            "endTime": row[5],
            "breakTime": row[6],
            "status": row[7],
            "calculation": {"totalHours": total_hours}
        })
    return jsonify({"status": "success", "shifts": shifts})

# シフト申請API
@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    data = request.get_json() or {}
    username = data.get('username')
    date = data.get('date')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    break_time = int(data.get('breakTime', 0))

    user = USERS.get(username)
    if not user:
        return jsonify({"status": "error", "message": "ユーザーが見つかりません。"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO shifts (username, name, date, start_time, end_time, break_time, status)
        VALUES (?, ?, ?, ?, ?, ?, 'applied')
    """, (username, user['name'], date, start_time, end_time, break_time))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "申請が完了しました。"})

# シフト申請取消API
@app.route('/api/shift-cancel', methods=['POST'])
def cancel_shift():
    data = request.get_json() or {}
    shift_id = data.get('shiftId')

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shifts WHERE id = ? AND status = 'applied'", (shift_id,))
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

# 管理者用：シフト状態更新API（確定 or 削除）
@app.route('/api/admin/shift-update', methods=['POST'])
def update_shift():
    data = request.get_json() or {}
    shift_id = data.get('shiftId')
    action = data.get('action') # 'confirm' or 'delete'

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if action == 'confirm':
        cursor.execute("UPDATE shifts SET status = 'confirmed' WHERE id = ?", (shift_id,))
    elif action == 'delete':
        cursor.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

# システム設定取得API
@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()

    settings = {row[0]: row[1] for row in rows}
    return jsonify({"status": "success", "settings": settings})

# 管理者用：システム設定更新API
@app.route('/api/admin/settings-update', methods=['POST'])
def update_settings():
    data = request.get_json() or {}
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for key, value in data.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

# アラート通知取得API
@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'deadlineDate'")
    row = cursor.fetchone()
    conn.close()

    deadline = row[0] if row else "未設定"
    alerts = [{"message": f"【お知らせ】シフト提出期限は「{deadline}」です。期限厳守でお願いいたします。"}]
    return jsonify({"status": "success", "alerts": alerts})

# 給与明細プレビューAPI（時給1,200円で簡易試算）
@app.route('/api/payslip', methods=['POST'])
def get_payslip():
    data = request.get_json() or {}
    username = data.get('username')

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 「確定」したシフトのみ対象
    cursor.execute("SELECT start_time, end_time, break_time FROM shifts WHERE username = ? AND status = 'confirmed'", (username,))
    rows = cursor.fetchall()
    conn.close()

    total_hours = 0.0
    for row in rows:
        try:
            sh, sm = map(int, row[0].split(':'))
            eh, em = map(int, row[1].split(':'))
            total_min = (eh * 60 + em) - (sh * 60 + sm) - int(row[2])
            total_hours += max(0, total_min / 60.0)
        except Exception:
            pass

    total_hours = round(total_hours, 1)
    hourly_rate = 1200
    total_pay = int(total_hours * hourly_rate)

    return jsonify({
        "status": "success",
        "totalHours": total_hours,
        "totalPay": total_pay
    })

if __name__ == '__main__':
    # 5001ポートでデバッグモード起動
    app.run(port=5001, debug=True)