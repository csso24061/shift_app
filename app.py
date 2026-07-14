import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# データベース設定 (SQLiteを使用)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'shift_system.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- データベースモデル定義 ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # ← エラーを修正（主キーを設定）
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)       # 'manager' または 'staff'
    hourly_rate = db.Column(db.Integer, default=1200)    # 時給設定

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(10), nullable=False)       # YYYY-MM-DD
    start_time = db.Column(db.String(5), nullable=False)   # HH:MM
    end_time = db.Column(db.String(5), nullable=False)     # HH:MM
    break_time = db.Column(db.Integer, default=60)        # 休憩（分）
    status = db.Column(db.String(20), default='applied')  # 'applied' または 'confirmed'

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deadline_date = db.Column(db.String(50), default='毎月20日')
    closing_date = db.Column(db.String(50), default='毎月末日')
    payment_date = db.Column(db.String(50), default='翌月15日')

# --- 補助関数 (労働時間・給与計算) ---
def calculate_hours_and_pay(start_str, end_str, break_mins, hourly_rate):
    try:
        fmt = '%H:%M'
        tdelta = datetime.strptime(end_str, fmt) - datetime.strptime(start_str, fmt)
        total_mins = tdelta.total_seconds() / 60
        actual_mins = total_mins - float(break_mins)
        if actual_mins < 0: actual_mins = 0
        
        hours = round(actual_mins / 60, 2)
        pay = int(hours * hourly_rate)
        return hours, pay
    except Exception:
        return 0, 0

# --- APIルート定義 ---

# 1. ログイン認証
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('userId'), password=data.get('password')).first()
    if user:
        return jsonify({
            'status': 'success',
            'user': {'username': user.username, 'name': user.name, 'role': user.role}
        })
    return jsonify({'status': 'error', 'message': 'IDまたはパスワードが間違っています'}), 401

# 2. シフト一覧取得 (FullCalendar用フォーマット)
@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    shifts = Shift.query.all()
    users = {u.username: u for u in User.query.all()}
    
    shift_list = []
    attendance_map = {} # スタッフごとの集計用

    for s in shifts:
        user = users.get(s.username)
        rate = user.hourly_rate if user else 1200
        hours, pay = calculate_hours_and_pay(s.start_time, s.end_time, s.break_time, rate)

        # カレンダー表示用データ
        shift_list.append({
            'id': str(s.id),
            'title': f"{s.name}\n{s.start_time}-{s.end_time}\n({hours}h)",
            'start': f"{s.date}T{s.start_time}:00",
            'end': f"{s.date}T{s.end_time}:00",
            'color': '#2ecc71' if s.status == 'confirmed' else '#f1c40f',
            'textColor': '#ffffff' if s.status == 'confirmed' else '#2c3e50',
            # 詳細保持用
            'username': s.username,
            'name': s.name,
            'date': s.date,
            'startTime': s.start_time,
            'endTime': s.end_time,
            'breakTime': s.break_time,
            'status': s.status
        })

        # 確定済みシフトのみ勤怠・給与に集計
        if s.status == 'confirmed':
            if s.username not in attendance_map:
                attendance_map[s.username] = {
                    'username': s.username,
                    'name': s.name,
                    'totalHours': 0.0,
                    'totalPay': 0,
                    'daysCount': 0
                }
            attendance_map[s.username]['totalHours'] += hours
            attendance_map[s.username]['totalPay'] += pay
            attendance_map[s.username]['daysCount'] += 1

    # 小数点以下の整形
    for k in attendance_map:
        attendance_map[k]['totalHours'] = round(attendance_map[k]['totalHours'], 2)

    return jsonify({
        'status': 'success',
        'shifts': shift_list,
        'attendance': list(attendance_map.values())
    })

# 3. スタッフ：シフト申請
@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if not user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません'}), 404

    new_shift = Shift(
        username=user.username,
        name=user.name,
        date=data.get('date'),
        start_time=data.get('startTime'),
        end_time=data.get('endTime'),
        break_time=int(data.get('breakTime', 60)),
        status='applied'
    )
    db.session.add(new_shift)
    db.session.commit()
    return jsonify({'status': 'success'})

# 4. スタッフ：申請の取り下げ
@app.route('/api/shift-cancel', methods=['POST'])
def cancel_shift():
    data = request.json
    shift = Shift.query.get(data.get('shiftId'))
    if shift and shift.status == 'applied':
        db.session.delete(shift)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': '取り下げ不可能なシフトです'}), 400

# 5. 管理者：シフトの確定・修正・削除
@app.route('/api/admin/shift-update', methods=['POST'])
def update_shift():
    data = request.json
    shift = Shift.query.get(data.get('shiftId'))
    if not shift:
        return jsonify({'status': 'error', 'message': 'シフトが見つかりません'}), 404

    action = data.get('action')
    if action == 'confirm':
        shift.status = 'confirmed'
    elif action == 'edit':
        shift.start_time = data.get('startTime')
        shift.end_time = data.get('endTime')
        shift.break_time = int(data.get('breakTime'))
    elif action == 'delete':
        db.session.delete(shift)
    
    db.session.commit()
    return jsonify({'status': 'success'})

# 6. システム設定取得
@app.route('/api/settings', methods=['GET'])
def get_settings():
    setting = SystemSetting.query.first()
    if not setting:
        setting = SystemSetting()
        db.session.add(setting)
        db.session.commit()
    return jsonify({
        'status': 'success',
        'settings': {
            'deadlineDate': setting.deadline_date,
            'closingDate': setting.closing_date,
            'payment_date': setting.payment_date
        }
    })

# 7. 管理者：システム設定更新
@app.route('/api/admin/settings-update', methods=['POST'])
def update_settings():
    data = request.json
    setting = SystemSetting.query.first()
    if not setting:
        setting = SystemSetting()
        db.session.add(setting)
    
    setting.deadline_date = data.get('deadlineDate')
    setting.closing_date = data.get('closingDate')
    setting.payment_date = data.get('paymentDate')
    db.session.commit()
    return jsonify({'status': 'success'})

# 8. アラート・通知の取得
@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    setting = SystemSetting.query.first()
    deadline = setting.deadline_date if setting else "毎月20日"
    return jsonify({
        'status': 'success',
        'alerts': [{'id': 1, 'message': f"【お知らせ】今月のシフト提出締め切り日は {deadline} です。厳守してください。"}]
    })

# --- 初期データの投入 ---
def init_db():
    db.create_all()
    # テスト用ユーザーの作成（未登録の場合のみ）
    if not User.query.filter_by(username='admin01').first():
        admin = User(username='admin01', password='adminpassword', name='管理者 太郎', role='manager', hourly_rate=0)
        staff1 = User(username='staff01', password='password123', name='スタッフ A子', role='staff', hourly_rate=1200)
        staff2 = User(username='staff02', password='password123', name='スタッフ B男', role='staff', hourly_rate=1300)
        
        db.session.add_all([admin, staff1, staff2])
        
        # サンプルシフト
        s1 = Shift(username='staff01', name='スタッフ A子', date='2026-07-15', start_time='10:00', end_time='18:00', break_time=60, status='confirmed')
        s2 = Shift(username='staff02', name='スタッフ B男', date='2026-07-16', start_time='13:00', end_time='21:00', break_time=60, status='applied')
        db.session.add_all([s1, s2])
        
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(port=5001, debug=True)