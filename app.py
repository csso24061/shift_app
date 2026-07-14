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

# 💾 運用スケジュール設定
system_settings = {
    "deadlineDate": "2026-07-25",  # シフト提出期限
    "closingDate": "末日",
    "paymentDate": "翌月15日"
}

# 💾 シフトデータを保存するリスト（一意のIDを持たせます）
# status: "applied" (希望中), "confirmed" (確定)
submitted_shifts = []
shift_id_counter = 1

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
    system_settings["deadlineDate"] = data.get('deadlineDate')
    system_settings["closingDate"] = data.get('closingDate')
    system_settings["paymentDate"] = data.get('paymentDate')
    return jsonify({"status": "success", "message": "設定を更新しました。", "settings": system_settings})

# 🔔 3日前リマインド通知API
@app.route('/api/notifications', methods=['POST'])
def get_notifications():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({"status": "error", "message": "ユーザー情報がありません"}), 400

    try:
        deadline_dt = datetime.strptime(system_settings["deadlineDate"], "%Y-%m-%d")
        remind_start_dt = deadline_dt - timedelta(days=3)
        today = datetime.now()
    except Exception:
        return jsonify({"status": "success", "alerts": []})

    alerts = []
    has_submitted = any(shift["username"] == username for shift in submitted_shifts)
    
    if today >= remind_start_dt and not has_submitted:
        alerts.append({
            "type": "warning",
            "message": f"⏳ 提出リマインド: シフト提出期限（{system_settings['deadlineDate']}）の3日前を過ぎています。まだ希望シフトが提出されていません。"
        })
    return jsonify({"status": "success", "alerts": alerts})

# 📥 希望シフト提出API
@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    global shift_id_counter
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
    if (end_h * 60 + end_m) <= (start_h * 60 + start_m):
        return jsonify({"status": "error", "message": "⚠️ 終了時間は開始時間より後にしてください。"}), 400

    # 給与計算
    total_hours = ((end_h * 60 + end_m) - (start_h * 60 + start_m)) / 60.0
    BASE_HOURLY_RATE = 1200
    basic_pay = total_hours * BASE_HOURLY_RATE  # 簡易計算

    new_shift = {
        "id": shift_id_counter,
        "username": username,
        "date": shift_date,
        "startTime": start_time,
        "endTime": end_time,
        "status": "applied",  # 初期値は「希望（applied）」
        "calculation": {
            "totalHours": round(total_hours, 1),
            "baseRate": BASE_HOURLY_RATE,
            "basicPay": int(basic_pay),
            "overtimePay": 0,
            "nightPay": 0,
            "totalPay": int(basic_pay)
        }
    }
    shift_id_counter += 1
    submitted_shifts.insert(0, new_shift)
    return jsonify({"status": "success", "data": new_shift})

# 🔄 シフト一覧取得API
@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    return jsonify({"status": "success", "shifts": submitted_shifts})

# 👑 【管理者専用】シフトステータス変更API（確定・編集・削除）
@app.route('/api/admin/shift-update', methods=['POST'])
def admin_update_shift():
    data = request.json
    shift_id = data.get('shiftId')
    action = data.get('action') # "confirm" (確定), "delete" (削除), "edit" (編集)
    
    global submitted_shifts
    target_shift = next((s for s in submitted_shifts if s["id"] == shift_id), None)
    
    if not target_shift:
        return jsonify({"status": "error", "message": "対象のシフトが見つかりません。"}), 404

    if action == "confirm":
        target_shift["status"] = "confirmed"
    elif action == "delete":
        submitted_shifts = [s for s in submitted_shifts if s["id"] != shift_id]
    elif action == "edit":
        target_shift["startTime"] = data.get('startTime')
        target_shift["endTime"] = data.get('endTime')
        # 簡易給与再計算
        sh, sm = map(int, target_shift["startTime"].split(':'))
        eh, em = map(int, target_shift["endTime"].split(':'))
        hours = ((eh * 60 + em) - (sh * 60 + sm)) / 60.0
        target_shift["calculation"]["totalHours"] = round(hours, 1)
        target_shift["calculation"]["totalPay"] = int(hours * 1200)

    return jsonify({"status": "success", "message": "シフトを更新しました。"})

# 👤 【スタッフ専用】確定シフトのキャンセル申請API（1週間前判定付き）
@app.route('/api/shift-cancel', methods=['POST'])
def cancel_shift():
    data = request.json
    shift_id = data.get('shiftId')
    
    global submitted_shifts
    target_shift = next((s for s in submitted_shifts if s["id"] == shift_id), None)
    
    if not target_shift:
        return jsonify({"status": "error", "message": "対象のシフトが見つかりません。"}), 404

    # 1週間前ルールの判定
    try:
        shift_dt = datetime.strptime(target_shift["date"], "%Y-%m-%d")
        today = datetime.now()
        # シフト当日より7日以上前かチェック
        if shift_dt - today < timedelta(days=7):
            return jsonify({
                "status": "error", 
                "message": "⚠️ 勤務日の1週間前を過ぎているため、システムから削除できません。管理者へ直接連絡してください。"
            }), 400
    except Exception as e:
        return jsonify({"status": "error", "message": "日付判定エラーが発生しました。"}), 500

    # 1週間前であれば削除
    submitted_shifts = [s for s in submitted_shifts if s["id"] != shift_id]
    return jsonify({"status": "success", "message": "シフトをキャンセルしました。"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)