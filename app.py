from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

USER_MASTER = {
    "staff01": {"password": "password123", "name": "山田 太郎", "role": "staff"},
    "staff02": {"password": "password456", "name": "佐藤 花子", "role": "staff"},
    "admin01": {"password": "adminpassword", "name": "管理者", "role": "manager"}
}

system_settings = {
    "deadlineDate": "2026-07-25",
    "closingDate": "末日",
    "paymentDate": "翌月15日"
}

submitted_shifts = []
shift_id_counter = 1

def calculate_salary(start_time_str, end_time_str):
    start_h, start_m = map(int, start_time_str.split(':'))
    end_h, end_m = map(int, end_time_str.split(':'))
    start_total = start_h * 60 + start_m
    end_total = end_h * 60 + end_m

    BASE_HOURLY_RATE = 1200
    BASE_MINUTE_RATE = BASE_HOURLY_RATE / 60.0

    total_minutes = end_total - start_total
    total_hours = total_minutes / 60.0

    basic_pay = 0.0
    overtime_pay = 0.0
    night_pay = 0.0
    current_time = start_total
    minutes_worked = 0
    
    while current_time < end_total:
        is_night = (1320 <= current_time < 1440)  # 22:00 ～ 24:00
        is_overtime = (minutes_worked >= 480)     # 8時間（480分）超過
        
        if is_overtime and is_night:
            basic_pay += BASE_MINUTE_RATE
            overtime_pay += BASE_MINUTE_RATE * 0.25
            night_pay += BASE_MINUTE_RATE * 0.25
        elif is_overtime:
            basic_pay += BASE_MINUTE_RATE
            overtime_pay += BASE_MINUTE_RATE * 0.25
        elif is_night:
            basic_pay += BASE_MINUTE_RATE
            night_pay += BASE_MINUTE_RATE * 0.25
        else:
            basic_pay += BASE_MINUTE_RATE
            
        current_time += 1
        minutes_worked += 1

    return {
        "totalHours": round(total_hours, 2),
        "baseRate": BASE_HOURLY_RATE,
        "basicPay": round(basic_pay),
        "overtimePay": round(overtime_pay),
        "nightPay": round(night_pay),
        "totalPay": round(basic_pay + overtime_pay + night_pay)
    }

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = USER_MASTER.get(data.get('userId'))
    if user and user["password"] == data.get('password'):
        return jsonify({"status": "success", "user": {"name": user["name"], "role": user["role"]}})
    return jsonify({"status": "error", "message": "⚠️ IDまたはパスワードが間違っています。"}), 401

@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify({"status": "success", "settings": system_settings})

@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    data = request.json
    username = data.get('username')
    try:
        deadline_dt = datetime.strptime(system_settings["deadlineDate"], "%Y-%m-%d")
        remind_start_dt = deadline_dt - timedelta(days=3)
        today = datetime.now()
    except Exception:
        return jsonify({"status": "success", "alerts": []})

    alerts = []
    has_submitted = any(shift["username"] == username for shift in submitted_shifts)
    if today >= remind_start_dt and not has_submitted:
        alerts.append({"type": "warning", "message": f"⏳ 提出リマインド: シフト提出期限（{system_settings['deadlineDate']}）の3日前を過ぎています。"})
    return jsonify({"status": "success", "alerts": alerts})

@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    global shift_id_counter
    data = request.json
    username = data.get('username')
    shift_date = data.get('date')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    
    if not username or not shift_date or not start_time or not end_time:
        return jsonify({"status": "error", "message": "⚠️ 入力項目が不足しています。"}), 400

    calc = calculate_salary(start_time, end_time)

    new_shift = {
        "id": shift_id_counter,
        "username": username,
        "date": shift_date,
        "startTime": start_time,
        "endTime": end_time,
        "status": "applied",
        "calculation": calc
    }
    shift_id_counter += 1
    submitted_shifts.insert(0, new_shift)
    return jsonify({"status": "success", "data": new_shift})

@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    return jsonify({"status": "success", "shifts": submitted_shifts})

@app.route('/api/admin/shift-update', methods=['POST'])
def admin_update_shift():
    data = request.json
    shift_id = data.get('shiftId')
    action = data.get('action')
    
    global submitted_shifts
    target_shift = next((s for s in submitted_shifts if s["id"] == shift_id), None)
    if not target_shift:
        return jsonify({"status": "error", "message": "シフトが見つかりません。"}), 404

    if action == "confirm":
        target_shift["status"] = "confirmed"
    elif action == "delete":
        submitted_shifts = [s for s in submitted_shifts if s["id"] != shift_id]
    elif action == "edit":
        target_shift["startTime"] = data.get('startTime')
        target_shift["endTime"] = data.get('endTime')
        target_shift["calculation"] = calculate_salary(target_shift["startTime"], target_shift["endTime"])

    return jsonify({"status": "success", "message": "シフトを更新しました。"})

@app.route('/api/shift-cancel', methods=['POST'])
def cancel_shift():
    data = request.json
    shift_id = data.get('shiftId')
    global submitted_shifts
    target_shift = next((s for s in submitted_shifts if s["id"] == shift_id), None)
    
    if not target_shift:
        return jsonify({"status": "error", "message": "シフトが見つかりません。"}), 404

    shift_dt = datetime.strptime(target_shift["date"], "%Y-%m-%d")
    if shift_dt - datetime.now() < timedelta(days=7):
        return jsonify({"status": "error", "message": "⚠️ 1週間前を過ぎているためシステムから削除できません。"}), 400

    submitted_shifts = [s for s in submitted_shifts if s["id"] != shift_id]
    return jsonify({"status": "success", "message": "シフトをキャンセルしました。"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)