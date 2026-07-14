from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shifts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------------------------------
# データベースモデル定義
# ----------------------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)

class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='applied')

# 設定保存用の新しいテーブル
class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    deadline_date = db.Column(db.String(50), default='毎月25日')
    closing_date = db.Column(db.String(50), default='月末')
    payment_date = db.Column(db.String(50), default='翌月15日')

# ----------------------------------------
# APIルート定義
# ----------------------------------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('userId')
    password = data.get('password')
    user = User.query.filter_by(username=username, password=password).first()
    if user:
        return jsonify({
            "status": "success",
            "user": { "username": user.username, "name": user.name, "role": user.role }
        }), 200
    return jsonify({"status": "error", "message": "IDまたはパスワードが違います"}), 401

@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    try:
        shifts = Shift.query.all()
        users = User.query.all()
        user_map = {u.username: u.name for u in users}
        results = []
        for s in shifts:
            try:
                fmt = '%H:%M'
                tdelta = datetime.strptime(s.end_time, fmt) - datetime.strptime(s.start_time, fmt)
                hours = max(0, tdelta.total_seconds() / 3600)
            except:
                hours = 0
            basic_pay = int(hours * 1200)
            results.append({
                "id": s.id, "username": s.username, "name": user_map.get(s.username, s.username),
                "date": s.date, "startTime": s.start_time, "endTime": s.end_time, "status": s.status,
                "calculation": { "totalHours": round(hours, 1), "totalPay": basic_pay, "basicPay": basic_pay, "overtimePay": 0, "nightPay": 0 }
            })
        return jsonify({"status": "success", "shifts": results}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/shift-submit', methods=['POST'])
def shift_submit():
    data = request.get_json() or {}
    new_shift = Shift(username=data.get('username'), date=data.get('date'), start_time=data.get('startTime'), end_time=data.get('endTime'), status='applied')
    db.session.add(new_shift)
    db.session.commit()
    return jsonify({"status": "success"}), 200

@app.route('/api/admin/shift-update', methods=['POST'])
def admin_shift_update():
    data = request.get_json() or {}
    shift = Shift.query.get(data.get('shiftId'))
    if not shift: return jsonify({"status": "error", "message": "Shift not found"}), 404
    action = data.get('action')
    if action == 'confirm': shift.status = 'confirmed'
    elif action == 'edit':
        shift.start_time = data.get('startTime')
        shift.end_time = data.get('endTime')
    elif action == 'delete': db.session.delete(shift)
    db.session.commit()
    return jsonify({"status": "success"}), 200

@app.route('/api/shift-cancel', methods=['POST'])
def shift_cancel():
    data = request.get_json() or {}
    shift = Shift.query.get(data.get('shiftId'))
    if shift and shift.status == 'applied':
        db.session.delete(shift)
        db.session.commit()
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "確定済みのシフトは削除できません"}), 400

# ⚙️ 設定の取得（データベースから取得するように変更）
@app.route('/api/settings', methods=['GET'])
def get_settings():
    setting = SystemSetting.query.first()
    if not setting:
        setting = SystemSetting()
        db.session.add(setting)
        db.session.commit()
    return jsonify({
        "status": "success",
        "settings": {"deadlineDate": setting.deadline_date, "closingDate": setting.closing_date, "paymentDate": setting.payment_date}
    }), 200

# ⚙️ 設定の更新用API（新設）
@app.route('/api/admin/settings-update', methods=['POST'])
def update_settings():
    data = request.get_json() or {}
    setting = SystemSetting.query.first()
    if not setting:
        setting = SystemSetting()
        db.session.add(setting)
    
    setting.deadline_date = data.get('deadlineDate', setting.deadline_date)
    setting.closing_date = data.get('closingDate', setting.closing_date)
    setting.payment_date = data.get('paymentDate', setting.payment_date)
    db.session.commit()
    return jsonify({"status": "success"}), 200

# 📢 通知（提出期限のアラート文面を設定に連動させる）
@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    setting = SystemSetting.query.first()
    dl = setting.deadline_date if setting else "25日"
    return jsonify({
        "status": "success",
        "alerts": [{"message": f"🚨 シフトの提出期限（{dl}）が近づいています。未提出の方は申請をお願いします。"}]
    }), 200

# ----------------------------------------
# データベース初期化とデモデータ投入
# ----------------------------------------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='staff01').first():
        db.session.add(User(username='staff01', password='password123', name='山田 太郎', role='staff'))
    if not User.query.filter_by(username='admin01').first():
        db.session.add(User(username='admin01', password='adminpassword', name='管理者', role='manager'))
    if not SystemSetting.query.first():
        db.session.add(SystemSetting()) # 初期設定データを投入
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5001)