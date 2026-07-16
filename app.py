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
    break_time = db.Column(db.Integer, default=0) # 休憩時間（分）
    status = db.Column(db.String(20), default='applied')

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    deadline_date = db.Column(db.String(50), default='毎月25日')
    closing_date = db.Column(db.String(50), default='月末')
    payment_date = db.Column(db.String(50), default='翌月15日')

# ----------------------------------------
# 補助関数
# ----------------------------------------
def parse_hours(start_time, end_time, break_minutes):
    """開始・終了・休憩時間から実労働時間を計算する"""
    try:
        fmt = '%H:%M'
        tdelta = datetime.strptime(end_time, fmt) - datetime.strptime(start_time, fmt)
        hours = max(0.0, (tdelta.total_seconds() / 3600) - (int(break_minutes) / 60))
        return round(hours, 1)
    except:
        return 0.0

def calculate_pay(start_time, end_time, break_minutes):
    """実労働時間と給与を計算する"""
    hours = parse_hours(start_time, end_time, break_minutes)
    basic_pay = int(hours * 1200)
    return hours, basic_pay

def get_week_range(date_str):
    """指定された日付（YYYY-MM-DD）が含まれる週（月曜日〜日曜日）の日付リストを返す"""
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    start_of_week = target_date - timedelta(days=target_date.weekday())
    return [(start_of_week + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

def check_labor_limits(username, date_str, start_time, end_time, break_time, exclude_shift_id=None):
    """法定労働時間（1日8時間・週40時間）を超えないかチェックする"""
    new_hours = parse_hours(start_time, end_time, break_time)
    
    # 1. 1日8時間チェック
    day_shifts = Shift.query.filter(Shift.username == username, Shift.date == date_str).all()
    day_total = 0.0
    for s in day_shifts:
        if exclude_shift_id and s.id == exclude_shift_id:
            continue
        day_total += parse_hours(s.start_time, s.end_time, s.break_time)
    
    if (day_total + new_hours) > 8.0:
        return False, f"【労働基準法違反エラー】1日の実労働時間が8時間を超えます（現在の日合計: {day_total + new_hours}時間）"

    # 2. 週40時間チェック
    week_days = get_week_range(date_str)
    week_shifts = Shift.query.filter(Shift.username == username, Shift.date.in_(week_days)).all()
    week_total = 0.0
    for s in week_shifts:
        if exclude_shift_id and s.id == exclude_shift_id:
            continue
        week_total += parse_hours(s.start_time, s.end_time, s.break_time)
        
    if (week_total + new_hours) > 40.0:
        return False, f"【労働基準法違反エラー】週の実労働時間が40時間を超えます（現在の週合計: {week_total + new_hours}時間）"
        
    return True, ""

# ----------------------------------------
# APIルート定義
# ----------------------------------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    user = User.query.filter_by(username=data.get('userId'), password=data.get('password')).first()
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
    username = data.get('username')
    date_str = data.get('date')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    break_time = int(data.get('breakTime', 0))

    existing_shift = Shift.query.filter_by(username=username, date=date_str).first()
    if existing_shift:
        return jsonify({
            "status": "error", 
            "message": "⚠️ この日は既にシフトが登録・申請されています（1人1日1個まで）。"
        }), 400

    is_valid, err_msg = check_labor_limits(username, date_str, start_time, end_time, break_time)
    if not is_valid:
        return jsonify({"status": "error", "message": err_msg}), 400

    new_shift = Shift(
        username=username, date=date_str, start_time=start_time, end_time=end_time, 
        break_time=break_time, status='applied'
    )
    db.session.add(new_shift)
    db.session.commit()
    return jsonify({"status": "success"}), 200

@app.route('/api/admin/shift-update', methods=['POST'])
def admin_shift_update():
    data = request.get_json() or {}
    shift = Shift.query.get(data.get('shiftId'))
    if not shift: 
        return jsonify({"status": "error", "message": "Shift not found"}), 404
        
    action = data.get('action')
    
    if action == 'confirm':
        break_time = int(data.get('breakTime', shift.break_time))
        is_valid, err_msg = check_labor_limits(shift.username, shift.date, shift.start_time, shift.end_time, break_time, exclude_shift_id=shift.id)
        if not is_valid:
            return jsonify({"status": "error", "message": err_msg}), 400
            
        shift.status = 'confirmed'
        shift.break_time = break_time
        
    elif action == 'edit':
        start_time = data.get('startTime')
        end_time = data.get('endTime')
        break_time = int(data.get('breakTime', 0))
        
        is_valid, err_msg = check_labor_limits(shift.username, shift.date, start_time, end_time, break_time, exclude_shift_id=shift.id)
        if not is_valid:
            return jsonify({"status": "error", "message": err_msg}), 400
            
        shift.start_time = start_time
        shift.end_time = end_time
        shift.break_time = break_time
        
    elif action == 'delete': 
        db.session.delete(shift)
        
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
    setting = SystemSetting.query.first() or SystemSetting()
    return jsonify({
        "status": "success",
        "settings": {"deadlineDate": setting.deadline_date, "closingDate": setting.closing_date, "paymentDate": setting.payment_date}
    }), 200

@app.route('/api/admin/settings-update', methods=['POST'])
def update_settings():
    data = request.get_json() or {}
    setting = SystemSetting.query.first() or SystemSetting()
    setting.deadline_date = data.get('deadlineDate', setting.deadline_date)
    setting.closing_date = data.get('closingDate', setting.closing_date)
    setting.payment_date = data.get('paymentDate', setting.payment_date)
    db.session.add(setting)
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
            # ★ 文字列内の「$」タイポを修正
            "date": s.date, "time": f"{s.start_time}～{s.end_time}",
            "breakTime": s.break_time, "hours": hours, "pay": pay
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
    
    # ★ 動作確認用：先月分の確定シフト（勤務実態）データがない場合は自動生成する
    if not Shift.query.filter_by(username='staff01').first():
        today = datetime.today()
        first_day_this_month = today.replace(day=1)
        # 先月の適当な日付（5日前）を計算して登録
        last_month_date = (first_day_this_month - timedelta(days=5)).strftime('%Y-%m-%d')
        db.session.add(Shift(
            username='staff01',
            date=last_month_date,
            start_time='09:00',
            end_time='18:00',
            break_time=60,
            status='confirmed'
        ))
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5001)