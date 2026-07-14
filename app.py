from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta

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
    date = db.Column(db.String(20), nullable=False) # YYYY-MM-DD
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    break_time = db.Column(db.Integer, default=0) # 休憩時間（分）※新設
    status = db.Column(db.String(20), default='applied')

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    deadline_date = db.Column(db.String(50), default='毎月25日')
    closing_date = db.Column(db.String(50), default='月末')
    payment_date = db.Column(db.String(50), default='翌月15日')

# ----------------------------------------
# 補助関数（給与計算：休憩時間をマイナスする）
# ----------------------------------------
def calculate_pay(start_time, end_time, break_minutes):
    try:
        fmt = '%H:%M'
        tdelta = datetime.strptime(end_time, fmt) - datetime.strptime(start_time, fmt)
        # 総時間（時間単位）から休憩時間（分を時間に変換）を引く
        hours = max(0.0, (tdelta.total_seconds() / 3600) - (break_minutes / 60))
    except:
        hours = 0.0
    basic_pay = int(hours * 1200)
    return round(hours, 1), basic_pay

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
            hours, basic_pay = calculate_pay(s.start_time, s.end_time, s.break_time)
            results.append({
                "id": s.id, "username": s.username, "name": user_map.get(s.username, s.username),
                "date": s.date, "startTime": s.start_time, "endTime": s.end_time, "breakTime": s.break_time,
                "status": s.status,
                "calculation": { "totalHours": hours, "totalPay": basic_pay, "basicPay": basic_pay, "overtimePay": 0, "nightPay": 0 }
            })
        return jsonify({"status": "success", "shifts": results}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/shift-submit', methods=['POST'])
def shift_submit():
    data = request.get_json() or {}
    # 新規申請時はデフォルトで休憩0分
    new_shift = Shift(
        username=data.get('username'), 
        date=data.get('date'), 
        start_time=data.get('startTime'), 
        end_time=data.get('endTime'), 
        break_time=int(data.get('breakTime', 0)),
        status='applied'
    )
    db.session.add(new_shift)
    db.session.commit()
    return jsonify({"status": "success"}), 200

@app.route('/api/admin/shift-update', methods=['POST'])
def admin_shift_update():
    data = request.get_json() or {}
    shift = Shift.query.get(data.get('shiftId'))
    if not shift: return jsonify({"status": "error", "message": "Shift not found"}), 404
    action = data.get('action')
    if action == 'confirm': 
        shift.status = 'confirmed'
        # 確定時に休憩時間（設定されていれば）を保存できるようにする
        if 'breakTime' in data:
            shift.break_time = int(data.get('breakTime'))
    elif action == 'edit':
        shift.start_time = data.get('startTime')
        shift.end_time = data.get('endTime')
        shift.break_time = int(data.get('breakTime', 0))
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

@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    setting = SystemSetting.query.first()
    dl = setting.deadline_date if setting else "25日"
    return jsonify({
        "status": "success",
        "alerts": [{"message": f"🚨 シフトの提出期限（{dl}）が近づいています。未提出の方は申請をお願いします。"}]
    }), 200

@app.route('/api/payslip', methods=['POST'])
def get_payslip():
    data = request.get_json() or {}
    username = data.get('username')
    
    today = datetime.today()
    first_day_this_month = today.replace(day=1)
    last_day_last_month = first_day_this_month - timedelta(days=1)
    last_month_str = last_day_last_month.strftime('%Y-%m')

    shifts = Shift.query.filter(
        Shift.username == username,
        Shift.status == 'confirmed',
        Shift.date.like(f"{last_month_str}%")
    ).order_by(Shift.date).all()

    total_hours = 0.0
    total_pay = 0
    details = []

    for s in shifts:
        hours, pay = calculate_pay(s.start_time, s.end_time, s.break_time)
        total_hours += hours
        total_pay += pay
        details.append({
            "date": s.date,
            "time": f"{s.start_time}～{s.end_time}",
            "breakTime": s.break_time,
            "hours": hours,
            "pay": pay
        })

    return jsonify({
        "status": "success",
        "targetMonth": last_month_str,
        "totalHours": round(total_hours, 1),
        "totalPay": total_pay,
        "details": details
    }), 200

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='staff01').first():
        db.session.add(User(username='staff01', password='password123', name='山田 太郎', role='staff'))
    if not User.query.filter_by(username='admin01').first():
        db.session.add(User(username='admin01', password='adminpassword', name='管理者', role='manager'))
    if not SystemSetting.query.first():
        db.session.add(SystemSetting())
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5001)