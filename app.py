from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    data = request.json
    shift_date = data.get('date')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    
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
    total_hours = total_minutes / 60.0 # 総労働時間(時間)

    basic_pay = 0
    overtime_pay = 0
    night_pay = 0
    
    # 15分ごとに細かく判定（計算の正確性を出すため）
    current_time = start_total
    minutes_worked = 0
    
    while current_time < end_total:
        # 現在の15分間が「深夜(22:00〜24:00＝1320分〜1440分)」かどうか
        is_night = (1320 <= current_time < 1440)
        # すでに8時間(480分)以上働いているか（残業判定）
        is_overtime = (minutes_worked >= 480)
        
        # 時給倍率の決定
        rate_multiplier = 1.0
        if is_overtime:
            rate_multiplier += 0.25
        if is_night:
            rate_multiplier += 0.25
            
        # 15分(0.25時間)分の給与を計算して加算
        segment_pay = (BASE_HOURLY_RATE * rate_multiplier) * 0.25
        
        # 内訳の記録
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

    return jsonify({
        "status": "success",
        "message": f"✅ {shift_date} のシフト希望を受付、給与を自動計算しました。",
        "data": {
            "date": shift_date,
            "startTime": start_time,
            "endTime": end_time,
            "calculation": {
                "totalHours": round(total_hours, 1),
                "baseRate": BASE_HOURLY_RATE,
                "basicPay": int(basic_pay),
                "overtimePay": int(overtime_pay),
                "nightPay": int(night_pay),
                "totalPay": int(total_pay)
            }
        }
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)