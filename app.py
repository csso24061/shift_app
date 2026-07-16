from flask import Flask, jsonify, request, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import traceback # エラー原因を特定するためのログ出力用

app = Flask(__name__)

# CORS設定（どこからアクセスしても遮断されないように設定）
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

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
    break_time = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='applied')

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    deadline_date = db.Column(db.String(50), default='毎月25日')
    closing_date = db.Column(db.String(50), default='月末')
    payment_date = db.Column(db.String(50), default='翌月15日')

# ----------------------------------------
# データベース接続の自動クリーンアップ（クラッシュ防止）
# ----------------------------------------
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

# ----------------------------------------
# 補助関数（エラーが起きても0を返す安全設計）
# ----------------------------------------
def parse_hours(start_time, end_time, break_minutes):
    try:
        fmt = '%H:%M'
        tdelta = datetime.strptime(end_time, fmt) - datetime.strptime(start_time, fmt)
        hours = max(0.0, (tdelta.total_seconds() / 3600) - (int(break_minutes) / 60))
        return round(hours, 1)
    except Exception as e:
        print(f"[ERROR] 時間計算に失敗しました: {e}")
        return 0.0

def calculate_pay(start_time, end_time, break_minutes):
    hours = parse_hours(start_time, end_time, break_minutes)
    basic_pay = int(hours * 1200)
    return hours, basic_pay

def get_week_range(date_str):
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        start_of_week = target_date - timedelta(days=target_date.weekday())
        return [(start_of_week + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    except Exception as e:
        print(f"[ERROR] 週範囲の取得に失敗しました: {e}")
        return []

def check_labor_limits(username, date_str, start_time, end_time, break_time, exclude_shift_id=None):
    try:
        new_hours = parse_hours(start_time, end_time, break_time)
        
        day_shifts = Shift.query.filter(Shift.username == username, Shift.date == date_str).all()
        day_total = 0.0
        for s in day_shifts:
            if exclude_shift_id and s.id == exclude_shift_id:
                continue
            day_total += parse_hours(s.start_time, s.end_time, s.break_time)
        
        if (day_total + new_hours) > 8.0:
            return False, f"【労働基準法違反エラー】1日の実労働時間が8時間を超えます（現在の日合計: {day_total + new_hours}時間）"

        week_days = get_week_range(date_str)
        if not week_days:
            return True, ""
            
        week_shifts = Shift.query.filter(Shift.username == username, Shift.date.in_(week_days)).all()
        week_total = 0.0
        for s in week_shifts:
            if exclude_shift_id and s.id == exclude_shift_id:
                continue
            week_total += parse_hours(s.start_time, s.end_time, s.break_time)
            
        if (week_total + new_hours) > 40.0:
            return False, f"【労働基準法違反エラー】週の実労働時間が40時間を超えます（現在の週合計: {week_total + new_hours}時間）"
            
        return True, ""
    except Exception as e:
        return False, f"労基法チェック中にエラーが発生しました: {str(e)}"

# ----------------------------------------
# 画面表示用のルート（絶対に落ちない try-except 構造）
# ----------------------------------------
@app.route('/')
def index():
    try:
        if os.path.exists('index.html'):
            return send_file('index.html')
        return "<h1>index.html が見つかりません</h1><p>app.pyと同じフォルダに置いてください。</p>", 404
    except Exception as e:
        traceback.print_exc()
        return f"システムエラーが発生しました: {str(e)}", 500

# ----------------------------------------
# APIルート定義（エラー時もクラッシュせず、正常に応答を返す）
# ----------------------------------------
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json() or {}
        user = User.query.filter_by(username=data.get('userId'), password=data.get('password')).first()
        if user:
            return jsonify({
                "status": "success",
                "user": { "username": user.username, "name": user.name, "role": user.role }
            }), 200
        return jsonify({"status": "error", "message": "IDまたはパスワードが違います"}), 401
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": "ログイン処理中にサーバーエラーが発生しました"}), 500

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
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"データ取得エラー: {str(e)}"}), 500

@app.route('/api/shift-submit', methods=['POST'])
def shift_submit():
    try:
        data = request.get_json() or {}
        username = data.get('username')
        date_str = data.get('date')
        start_time = data.get('startTime')
        end_time = data.get('endTime')
        break_time = int(data.get('breakTime', 0))

        existing_shift = Shift.query.filter_by(username=username, date=date_str).first()
        if existing_shift:
            return jsonify({"status": "error", "message": "⚠️ この日は既にシフトが登録・申請されています。"}), 400

        is_valid, err_msg = check_labor_limits(username, date_str, start_time, end_time, break_time)
        if not is_valid:
            return jsonify({"status": "error", "message": err_msg}), 400

        new_shift = Shift(username=username, date=date_str, start_time=start_time, end_time=end_time, break_time=break_time, status='applied')
        db.session.add(new_shift)
        db.session.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"申請エラー: {str(e)}"}), 500

@app.route('/api/admin/shift-update', methods=['POST'])
def admin_shift_update():
    try:
        data = request.get_json() or {}
        shift = Shift.query.get(data.get('shiftId'))
        if not shift: 
            return jsonify({"status": "error", "message": "シフトデータが見つかりません"}), 404
            
        action = data.get('action')
        if action == 'confirm':
            break_time = int(data.get('breakTime', shift.break_time))
            is_valid, err_msg = check_labor_limits(shift.username, shift.date, shift.start_time, shift.end_time, break_time, exclude_shift_id=shift.id)
            if not is_valid: return jsonify({"status": "error", "message": err_msg}), 400
            shift.status = 'confirmed'
            shift.break_time = break_time
        elif action == 'edit':
            start_time = data.get('startTime')
            end_time = data.get('endTime')
            break_time = int(data.get('breakTime', 0))
            is_valid, err_msg = check_labor_limits(shift.username, shift.date, start_time, end_time, break_time, exclude_shift_id=shift.id)
            if not is_valid: return jsonify({"status": "error", "message": err_msg}), 400
            shift.start_time = start_time
            shift.end_time = end_time
            shift.break_time = break_time
        elif action == 'delete': 
            db.session.delete(shift)
            
        db.session.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"更新エラー: {str(e)}"}), 500

@app.route('/api/shift-cancel', methods=['POST'])
def shift_cancel():
    try:
        data = request.get_json() or {}
        shift = Shift.query.get(data.get('shiftId'))
        if shift and shift.status == 'applied':
            db.session.delete(shift)
            db.session.commit()
            return jsonify({"status": "success"}), 200
        return jsonify({"status": "error", "message": "確定済みのシフトは削除できません"}), 400
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"キャンセルエラー: {str(e)}"}), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    try:
        setting = SystemSetting.query.first() or SystemSetting()
        return jsonify({
            "status": "success",
            "settings": {"deadlineDate": setting.deadline_date, "closingDate": setting.closing_date, "paymentDate": setting.payment_date}
        }), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"設定取得エラー: {str(e)}"}), 500

@app.route('/api/admin/settings-update', methods=['POST'])
def update_settings():
    try:
        data = request.get_json() or {}
        setting = SystemSetting.query.first() or SystemSetting()
        setting.deadline_date = data.get('deadlineDate', setting.deadline_date)
        setting.closing_date = data.get('closingDate', setting.closing_date)
        setting.payment_date = data.get('paymentDate', setting.payment_date)
        db.session.add(setting)
        db.session.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"設定更新エラー: {str(e)}"}), 500

@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    try:
        setting = SystemSetting.query.first()
        dl = setting.deadline_date if setting else "25日"
        return jsonify({
            "status": "success",
            "alerts": [{"message": f"🚨 シフトの提出期限（{dl}）が近づいています。未提出の方は申請をお願いします。"}]
        }), 200
    except Exception as e:
        return jsonify({"status": "success", "alerts": []}), 200

@app.route('/api/payslip', methods=['POST'])
def get_payslip():
    try:
        data = request.get_json() or {}
        username = data.get('username')
        today = datetime.today()
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        last_month_str = last_day_last_month.strftime('%Y-%m')

        shifts = Shift.query.filter(Shift.username == username, Shift.status == 'confirmed', Shift.date.like(f"{last_month_str}%")).order_by(Shift.date).all()
        total_hours = 0.0
        total_pay = 0
        details = []
        for s in shifts:
            hours, pay = calculate_pay(s.start_time, s.end_time, s.break_time)
            total_hours += hours
            total_pay += pay
            details.append({"date": s.date, "time": f"{s.start_time}～{s.end_time}", "breakTime": s.break_time, "hours": hours, "pay": pay})

        return jsonify({"status": "success", "targetMonth": last_month_str, "totalHours": round(total_hours, 1), "totalPay": total_pay, "details": details}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"明細取得エラー: {str(e)}"}), 500

# ----------------------------------------
# データベースと初期データの作成
# ----------------------------------------
with app.app_context():
    try:
        db.create_all()
        if not User.query.filter_by(username='staff01').first():
            db.session.add(User(username='staff01', password='password123', name='山田 太郎', role='staff'))
        if not User.query.filter_by(username='admin01').first():
            db.session.add(User(username='admin01', password='adminpassword', name='管理者', role='manager'))
        db.session.commit()
    except Exception as e:
        print(f"[FATAL] データベース初期化に失敗しました: {e}")

if __name__ == '__main__':
    # debug=True は、構文エラーがあった際に自動でリロードしてくれます。
    # host='0.0.0.0' にすることで、どのIP/localhostからでも安定してアクセス可能になります。
    app.run(debug=True, host='0.0.0.0', port=5001)