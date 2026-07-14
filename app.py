from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import calendar

app = Flask(__name__)

# データベース設定 (SQLiteを使用)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shifts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------------------------------
# データベースモデル定義 (テーブル構造)
# ----------------------------------------

# ユーザー情報テーブル
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False) # 'staff01' など
    name = db.Column(db.String(100), nullable=False)                 # '山田 太郎' など
    role = db.Column(db.String(20), nullable=False)                  # 'manager' または 'staff'

# シフト情報テーブル
class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)                        # '2026-07-10' など
    hours = db.Column(db.Integer, default=0)                         # 労働時間
    pay = db.Column(db.Integer, default=0)                           # 給与（または時給から計算）
    status = db.Column(db.String(20), default='pending')             # 'confirmed' または 'pending'

    # リレーションシップ定義 (Userテーブルと紐付け)
    user = db.relationship('User', backref=db.backref('shifts', lazy=True))


# ----------------------------------------
# APIルート定義
# ----------------------------------------

# 【修正】既存の「/api/shifts」のレスポンスに、各ユーザーのフルネーム情報を含める
@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    try:
        # ShiftとUserをJOIN（結合）してデータを一括取得
        shifts_data = db.session.query(Shift, User).join(User, Shift.user_id == User.id).all()
        
        results = []
        for shift, user in shifts_data:
            results.append({
                "id": shift.id,
                "username": user.username,
                "name": user.name,          # 各ユーザーのフルネームを追加
                "date": shift.date.strftime('%Y-%m-%d'),
                "hours": shift.hours,
                "pay": shift.pay,
                "status": shift.status
            })
            
        return jsonify({
            "status": "success",
            "shifts": results
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 【新規追加】CSV用の前月データ取得API
@app.route('/api/past-month-summary', methods=['POST'])
def past_month_summary():
    data = request.get_json() or {}
    username = data.get('username')
    role = data.get('role')
    
    if not username or not role:
        return jsonify({"status": "error", "message": "Missing username or role"}), 400
        
    try:
        # 1. 前月（先月）の期間を計算
        today = date.today()
        # 今月の1日を取得
        first_day_of_this_month = today.replace(day=1)
        # 先月の最終日（今月1日の1日前）を取得
        last_day_of_past_month = first_day_of_this_month - timedelta(days=1)
        # 先月の1日を取得
        first_day_of_past_month = last_day_of_past_month.replace(day=1)
        
        # 2. 基本のクエリを作成 (前月の期間内 ＆ 確定済み)
        query = db.session.query(Shift, User).join(User, Shift.user_id == User.id)\
            .filter(Shift.date >= first_day_of_past_month)\
            .filter(Shift.date <= last_day_of_past_month)\
            .filter(Shift.status == 'confirmed')
            
        # 3. roleによるフィルタリング
        # managerの場合はそのまま全員分、staffの場合は自分のusernameのみ
        if role != 'manager':
            query = query.filter(User.username == username)
            
        shifts_data = query.all()
        
        # フロント側でCSV変換しやすいように整形
        formatted_data = []
        for shift, user in shifts_data:
            formatted_data.append({
                "name": user.name,
                "date": shift.date.strftime('%Y-%m-%d'),
                "hours": shift.hours,
                "pay": shift.pay
            })
            
        return jsonify({
            "status": "success",
            "data": formatted_data
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ----------------------------------------
# データベース初期化とデモデータ投入（確認用）
# ----------------------------------------
def init_db():
    with app.app_context():
        db.create_all()
        
        # すでにデータがある場合はスキップ
        if User.query.first():
            return
            
        # デモユーザー
        manager = User(username='admin', name='管理 太郎', role='manager')
        staff1 = User(username='staff01', name='山田 太郎', role='staff')
        staff2 = User(username='staff02', name='鈴木 花子', role='staff')
        db.session.add_all([manager, staff1, staff2])
        db.session.commit()
        
        # デモシフト (当月と前月のデータを投入)
        today = date.today()
        past_month_date = (today.replace(day=1) - timedelta(days=15)) # 確実に前月になる日付
        
        s1 = Shift(user_id=staff1.id, date=today, hours=8, pay=9600, status='pending')
        s2 = Shift(user_id=staff1.id, date=past_month_date, hours=8, pay=9600, status='confirmed')
        s3 = Shift(user_id=staff2.id, date=past_month_date, hours=6, pay=7200, status='confirmed')
        db.session.add_all([s1, s2, s3])
        db.session.commit()

if __name__ == '__main__':
    init_db() # 起動時にデータベースと初期データを準備
    app.run(debug=True, port=5000)