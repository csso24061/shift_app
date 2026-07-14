from flask import Flask, request, jsonify
from flask_cors import CORS # フロントとバックの接続を許可するライブラリ

app = Flask(__name__)
CORS(app) # 異なるポート間での通信エラー（CORSエラー）を防ぎます

@app.route('/api/shift-submit', methods=['POST'])
def submit_shift():
    data = request.json
    
    # 1. データの受信
    shift_date = data.get('date')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    
    # 2. 【検証①】空データのチェック
    if not shift_date or not start_time or not end_time:
        return jsonify({
            "status": "error",
            "message": "⚠️ 日付と時間が正しく入力されていません。"
        }), 400

    # 時間を比較するために「分」に変換する処理
    try:
        start_h, start_m = map(int, start_time.split(':'))
        end_h, end_m = map(int, end_time.split(':'))
        start_total = start_h * 60 + start_m
        end_total = end_h * 60 + end_m
    except ValueError:
        return jsonify({
            "status": "error",
            "message": "⚠️ 時間の形式が不正です。"
        }), 400

    # 3. 【検証②】時間の逆転チェック
    if end_total <= start_total:
        return jsonify({
            "status": "error",
            "message": "⚠️ 終了時間は、開始時間よりも後の時間を設定してください。"
        }), 400

    # 全ての検証をパスした場合
    return jsonify({
        "status": "success",
        "message": f"✅ {shift_date} {start_time}〜{end_time} のシフト希望を受け付けました（Flaskで計算完了）",
        "data": {
            "date": shift_date,
            "startTime": start_time,
            "endTime": end_time
        }
    })

if __name__ == '__main__':
    # ポート5000番でサーバーを起動します
    app.run(debug=True, port=5000)