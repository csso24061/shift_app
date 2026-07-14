from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 💾 メモリ上に簡易的にデータを保存するリスト（サーバーを再起動するとリセットされます）
# 本格的な運用の場合は将来的にデータベース（SQLiteなど）へ保存します。
submitted_shifts = []

@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    data = request.json
    username = data.get('username')  # ログインしているユーザー名
    shift_date = data.get('date')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    
    if not username:
        return jsonify({"status": "error", "message": "⚠️ ログイン情報がありません。再度ログインしてください。"}), 401
    if not shift_date or not start_time or not end_time:
        return jsonify({"status": "error", "message": "⚠️ 日付と時間が正しく入力されていません。"}), 400

    # 時間を「分」に変換
    start_h, start_m = map(int, start_time.split(':'))
    end_h, end_m = map(int, end_time.split(':'))
    start_total = start_h * 60 + start_m
    end_total = end_h * 60 + end_m

    if end_total <= start_total:
        return jsonify({"status": "error", "message": "⚠️ 終了時間は、開始時間よりも後の時間を設定してください。"}), 400

    # ====== 💰 給与自動計算ロジック (30分刻み対応) ======
    BASE_HOURLY_RATE = 1200  # 基本時給
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
        if is_overtime:
            rate_multiplier += 0.25
        if is_night:
            rate_multiplier += 0.25
            
        segment_pay = (BASE_HOURLY_RATE * rate_multiplier) * 0.25
        
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

    total_pay = basic_pay + overtime_pay + night_pay

    calculation_result = {
        "totalHours": round(total_hours, 1),
        "baseRate": BASE_HOURLY_RATE,
        "basicPay": int(basic_pay),
        "overtimePay": int(overtime_pay),
        "nightPay": int(night_pay),
        "totalPay": int(total_pay)
    }

    # データを保存用の辞書にまとめる
    new_shift = {
        "username": username,
        "date": shift_date,
        "startTime": start_time,
        "endTime": end_time,
        "calculation": calculation_result
    }
    
    # サーバーのリストに保存（最新のものが先頭にくるように挿入）
    submitted_shifts.insert(0, new_shift)

    return jsonify({
        "status": "success",
        "message": f"✅ {shift_date} のシフト希望を受付、給与を自動計算しました。",
        "data": new_shift
    })

# 🔄 保存されているすべてのシフト履歴を取得するAPI（店長用、および各スタッフのフィルター用）
@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    return jsonify({"status": "success", "shifts": submitted_shifts})

if __name__ == '__main__':
    app.run(debug=True, port=5000)