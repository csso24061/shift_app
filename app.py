from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app) # フロントエンド（HTMLファイル）からの通信を許可

# データベース設定 (SQLiteを使用)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shifts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------------------------------
# データベースモデル定義
# ----------------------------------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False) # 'staff01', 'admin01'
    password = db.Column(db.String(100), nullable=False)            # 'password123'
    name = db.Column(db.String(100), nullable=False)                 # '山田 太郎'
    role = db.Column(db.String(20), nullable=False)                  # 'manager', 'staff'

class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)              # 申請者のユーザーID
    date = db.Column(db.String(20), nullable=False)                  # '2026-07-14'
    start_time = db.Column(db.String(10), nullable=False)            # '09:00'
    end_time = db.Column(db.String(10), nullable=False)              # '18:00'
    status = db.Column(db.String(20), default='applied')             # 'applied', 'confirmed'

# ----------------------------------------
# APIルート定義
# ----------------------------------------

# 🔓 ログインAPI（不具合対策：ユーザー情報と役割、フルネームを確実に返す）
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('userId')
    password = data.get('password')

    user = User.query.filter_by(username=username, password=password).first()
    if user:
        return jsonify({
            "status": "success",
            "user": {
                "username": user.username,
                "name": user.name,
                "role": user.role
            }
        }), 200
    else:
        return jsonify({"status": "error", "message": "IDまたはパスワードが違います"}), 401

# 📅 シフト一覧取得API（ユーザー情報をマッピングしてフルネームを含めて返す）
@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    try:
        shifts = Shift.query.all()
        # ユーザーIDからフルネームを引くための辞書を作成
        users = User.query.all()
        user_map = {u.username: u.name for u in users}

        results = []
        for s in shifts:
            # 勤務時間から簡単な給与計算ロジック（時給1,200円固定、深夜手当などの仮計算）
            try:
                fmt = '%H:%M'
                tdelta = datetime.strptime(s.end_time, fmt) - datetime.strptime(s.start_time, fmt)
                hours = max(0, tdelta.total_seconds() / 3600)
            except:
                hours = 0
            
            basic_pay = int(hours * 1200)
            total_pay = basic_pay

            results.append({
                "id": s.id,
                "username": s.username,
                "name": user_map.get(s.username, s.username), # フルネームをマッピング（なければID）
                "date": s.date,
                "startTime": s.start_time,
                "endTime": s.end_time,
                "status": s.status,
                "calculation": {
                    "totalHours": round(hours, 1),
                    "totalPay": total_pay,
                    "basicPay": basic_pay,
                    "overtimePay": 0,
                    "nightPay": 0
                }
            })
        return jsonify({"status": "success", "shifts": results}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 📝 シフト申請・登録API
@app.route('/api/shift-submit', methods=['POST'])
def shift_submit():
    data = request.get_json() or {}
    new_shift = Shift(
        username=data.get('username'),
        date=data.get('date'),
        start_time=data.get('startTime'),
        end_time=data.get('endTime'),
        status='applied'
    )
    db.session.add(new_shift)
    db.session.commit()
    return jsonify({"status": "success"}), 200

# ⚙️ 管理者用：シフト更新・削除API
@app.route('/api/admin/shift-update', methods=['POST'])
def admin_shift_update():
    data = request.get_json() or {}
    shift_id = data.get('shiftId')
    action = data.get('action')
    
    shift = Shift.query.get(shift_id)
    if not shift:
        return jsonify({"status": "error", "message": "Shift not found"}), 404
        
    if action == 'confirm':
        shift.status = 'confirmed'
    elif action == 'edit':
        shift.start_time = data.get('startTime')
        shift.end_time = data.get('endTime')
    elif action == 'delete':
        db.session.delete(shift)
        
    db.session.commit()
    return jsonify({"status": "success"}), 200

# ❌ スタッフ自身による申請キャンセルAPI
@app.route('/api/shift-cancel', methods=['POST'])
def shift_cancel():
    data = request.get_json() or {}
    shift = Shift.query.get(data.get('shiftId'))
    if shift and shift.status == 'applied':
        db.session.delete(shift)
        db.session.commit()
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "確定済みのシフトは削除できません"}), 400

# 📢 各種ダミー設定・通知用API
@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify({
        "status": "success",
        "settings": {"deadlineDate": "毎月25日", "closingDate": "月末", "paymentDate": "翌月15日"}
    }), 200

@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    # 25日直前の提出期限ポップアップ用ダミーアラート
    return jsonify({
        "status": "success",
        "alerts": [{"message": "🚨 シフトの提出期限（25日）が近づいています。未提出の方は申請をお願いします。"}]
    }), 200

# ----------------------------------------
# データベース初期化とデモデータ投入
# ----------------------------------------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='staff01').first():
        staff = User(username='staff01', password='password123', name='山田 太郎', role='staff')
        admin = User(username='admin01', password='password123', name='管理 花子', role='manager')
        db.session.add(staff)
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)