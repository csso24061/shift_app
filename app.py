from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# 🔑 サンプル用のユーザーマスターデータ
USER_MASTER = {
    "staff01": {"password": "password123", "name": "山田 太郎", "role": "staff"},
    "staff02": {"password": "password456", "name": "佐藤 花子", "role": "staff"},
    "admin01": {"password": "adminpassword", "name": "管理者", "role": "manager"}
}

# 💾 運用スケジュール設定の初期値
system_settings = {
    "deadlineDate": "2026-07-25",  # シフト提出期限
    "closingDate": "末日",         # 給与締め日
    "paymentDate": "翌月15日"       # 給与振込日
}

# 💾 シフトデータを保存するリスト
submitted_shifts = []

# 🔒 ログイン認証API
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_id = data.get('userId')
    password = data.get('password')

    if not user_id or not password:
        return jsonify({"status": "error", "message": "⚠️ IDとパスワードを入力してください。"}), 400

    user = USER_MASTER.get(user_id)
    if user and user["password"] == password:
        return jsonify({
            "status": "success",
            "message": "ログインに成功しました。",
            "user": {
                "name": user["name"],
                "role": user["role"]
            }
        }), 200
    else:
        return jsonify({"status": "error", "message": "⚠️ IDまたはパスワードが間違っています。"}), 401

# ⚙️ 設定取得API
@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify({"status": "success", "settings": system_settings})

# ⚙️ 設定更新API
@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    deadline = data.get('deadlineDate')
    closing = data.get('closingDate')
    payment = data.get('paymentDate')

    if not deadline or not closing or not payment:
        return jsonify({"status": "error", "message": "⚠️ すべての項目を入力してください。"}), 400

    system_settings["deadlineDate"] = deadline
    system_settings["closingDate"] = closing
    system_settings["paymentDate"] = payment

    return jsonify({"status": "success", "message": "設定を更新しました。", "settings": system_settings})

# 🔔 3日前リマインド通知API (新規追加)
@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({"status": "error", "message": "ユーザー情報がありません"}), 400

    # 期限日の3日前を計算
    try:
        deadline_dt = datetime.strptime(system_settings["deadlineDate"], "%Y-%m-%d")
        remind_start_dt = deadline_dt - timedelta(days=3)
        today = datetime.now() # テスト用：本日が期限3日前〜期限当日までの間か判定
    except Exception:
        return jsonify({"status": "success", "alerts": []})

    alerts = []
    
    # 対象ユーザーがすでにシフトを出しているか確認
    has_submitted = any(shift["username"] == username for shift in submitted_shifts)
    
    # 【判定条件】本日が「期限3日前」以降、かつ「未提出」の場合に通知を発動
    if today >= remind_start_dt and not has_submitted:
        alerts.append({
            "type": "warning",
            "message": f"⏳ 提出リマインド: シフト提出期限（{system_settings['deadlineDate']}）の3日前を過ぎています。まだ希望シフトが提出されていません。早めの提出をお願いします！"
        })

    return jsonify({"status": "success", "alerts": alerts})

@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    data = request.json
    username = data.get('username')
    shift_date = data.get('date')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    
    if not username:
        return jsonify({"status": "error", "message": "⚠️ ログイン情報がありません。"}), 401
    if not shift_date or not start_time or not end_time:
        return jsonify({"status": "error", "message": "⚠️ 入力項目が不足しています。"}), 400

    start_h, start_m = map(int, start_time.split(':'))
    end_h, end_m = map(int, end_time.split(':'))
    start_total = start_h * 60 + start_m
    end_total = end_h * 60 + end_m

    if end_total <= start_total:
        return jsonify({"status": "error", "message": "⚠️ 終了時間は開始時間より後にしてください。"}), 400

    BASE_HOURLY_RATE = 1200
    total_minutes = end_total - start_total
    total_hours = total_minutes / 60.0

    basic_pay = 0
    overtime_pay = 0
    night_pay = 0
    current_time = start_total
    minutes_worked = 0
    
    while current_time < end_total:
        is_night = (1320 <= current_time < 1440)
        is_overtime = (minutes_worked >= 480)
        
        rate_multiplier = 1.0
        if is_overtime: rate_multiplier += 0.25
        if is_night: rate_multiplier += 0.25
            
        if is_overtime and is_night:
            overtime_pay += (BASE_HOURLY_RATE * 0.25) * 0.25
            night_pay += (BASE_HOURLY_RATE * 0.25) * 0.25
            basic_pay += (BASE_HOURLY_RATE * 1.0) * 0.25
        elif is_overtime:
            overtime_pay += (BASE_HOURLY_RATE * 0.25) * 0.25
            basic_pay += (BASE_HOURLY_RATE * 1.0) * 0.25
        elif is_night:
            night_pay += (BASE_HOURLY_RATE * 0.25) * 0.25
            basic_pay += (BASE_HOURLY_RATE * 1.0) * 0.25
        else:
            basic_pay += (BASE_HOURLY_RATE * 1.0) * 0.25
            
        current_time += 15
        minutes_worked += 15

    calculation_result = {
        "totalHours": round(total_hours, 1),
        "baseRate": BASE_HOURLY_RATE,
        "basicPay": int(basic_pay),
        "overtimePay": int(overtime_pay),
        "nightPay": int(night_pay),
        "totalPay": int(basic_pay + overtime_pay + night_pay)
    }

    new_shift = {
        "username": username,
        "date": shift_date,
        "startTime": start_time,
        "endTime": end_time,
        "calculation": calculation_result
    }
    
    submitted_shifts.insert(0, new_shift)
    return jsonify({"status": "success", "data": new_shift})

@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    return jsonify({"status": "success", "shifts": submitted_shifts})

if __name__ == '__main__':
    app.run(debug=True, port=5000)