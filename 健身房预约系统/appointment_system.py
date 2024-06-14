from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import pyodbc
import json
from datetime import datetime
import pymssql

app = Flask(__name__)
CORS(app)

# SQL Server 连接配置
server = 'localhost'
database = 'appointment_system'
username = 'sa'
password = 'WSWwsw030809'
conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=' + server + ';DATABASE=' + database + ';UID=' + username + ';PWD=' + password)

account = None
day = None

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    new_username = data.get('username')
    new_password = data.get('password')

    # 简单的输入验证
    if not new_username or not new_password:
        return jsonify({'error': '需要提供用户名和密码'}), 400

    cursor = conn.cursor()

    # 检查用户名是否已存在
    cursor.execute("SELECT COUNT(1) FROM Users WHERE Username = ?", new_username)
    if cursor.fetchone()[0] > 0:
        return jsonify({'error': '用户名已存在'}), 400

    # 插入新用户
    cursor.execute("INSERT INTO Users (Username, PasswordHash) VALUES (?, ?)", (new_username, new_password))
    conn.commit()

    return jsonify({'message': '注册成功'}), 201

@app.route('/login', methods=['POST'])
def login():
    global account
    data = request.json
    username = data.get('username')
    password = data.get('password')

    cursor = conn.cursor()
    cursor.execute("SELECT PasswordHash FROM Users WHERE Username = ?", username)
    user = cursor.fetchone()

    if user and user[0] == password:
        account = username
        return jsonify({'message': '登录成功'}), 200
    else:
        return jsonify({'error': '无效的用户名或密码'}), 401



# Flask 应用的其他部分保持不变

@app.route('/book', methods=['POST'])
def book():
    data = request.json
    facility = data.get('facility')
    time = data.get('time')

    cursor = conn.cursor()
    cursor.execute("UPDATE FacilityBooking SET AvailableSpots = AvailableSpots - 1 WHERE Facility = ? AND TimeSlot = ?", (facility, time))
    conn.commit()

    return jsonify({'message': '预约成功'}), 200

@app.route('/appointments/availability/<facility>', methods=['POST'])
def availability(facility):
    data = request.json
    if len(data) == 0:
        date_index = 0
    else:
        date_index = data['dateIndex']  # 从请求体获取 dateIndex
    print(data)
    global day
    day = date_index
    cursor = conn.cursor()
    query = "SELECT TimeSlot, AvailableSpots FROM FacilityBooking WHERE Facility = ? AND dateindex = ?"
    cursor.execute(query, (facility, date_index))
    rows = cursor.fetchall()

    availability_data = [{'TimeSlot': row[0], 'AvailableSpots': row[1]} for row in rows]

    return jsonify(availability_data)

# 使用列表存储预约信息
appointments = []
@app.route('/confirm_booking', methods=['POST'])
def confirm_booking():
    global account
    if not account:
        return jsonify({'error': '用户未登录'}), 401

    data = request.json
    facility = data.get('facility')
    facility = facility.split('\n')[0]
    time = data.get('time')

    # 减少 FacilityBooking 表中的可用名额
    cursor = conn.cursor()
    cursor.execute("UPDATE FacilityBooking SET AvailableSpots = AvailableSpots - 1 WHERE Facility = ? AND TimeSlot = ? AND dateindex = ?",(facility,time, day))
    conn.commit()

    # 在 UserBookings 表中添加记录
    cursor.execute("INSERT INTO UserBookings (Username, Facility, TimeSlot, Status, dateindex) VALUES (?, ?, ?, '预约', ?)", (account, facility, time, day))
    conn.commit()

    return jsonify({'message': '预约成功'})

@app.route('/user_appointments', methods=['GET'])
def user_appointments():
    global account
    if not account:
        return jsonify({'error': '用户未登录'}), 401

    cursor = conn.cursor()
    cursor.execute("SELECT Facility, TimeSlot, Status,dateindex FROM UserBookings WHERE Username = ?", account)
    appointments = cursor.fetchall()

    appointments_list = [{'location': row[0], 'time': row[1], 'status': row[2], 'dateindex':row[3]} for row in appointments]

    return jsonify(appointments_list)

@app.route('/confirm_completion', methods=['POST'])
def confirm_completion():
    global account
    data = request.json
    facility = data['facility']
    time = data['time']
    date = datetime.now().strftime('%Y-%m-%d')  # 获取当前日期

    cursor = conn.cursor()

    # 更新 UserBookings 表
    cursor.execute("UPDATE UserBookings SET Status = '已完成' WHERE Username = ? AND Facility = ? AND TimeSlot = ?", (account, facility, time))

    # 向 UserSchedule 表中插入新数据
    cursor.execute("INSERT INTO UserSchedule (Users, Date, Location, Time) VALUES (?, ?, ?, ?)", (account, date, facility, time))

    # 检查 score 表中是否已有当前用户的记录
    cursor.execute("SELECT point FROM score WHERE Users = ?", account)
    result = cursor.fetchone()

    if result:
        # 如果用户存在，则更新积分
        new_point = result[0] + 1
        cursor.execute("UPDATE score SET point = ? WHERE Users = ?", (new_point, account))
    else:
        # 如果用户不存在，则插入新记录
        cursor.execute("INSERT INTO score (Users, point) VALUES (?, ?)", (account, 1))

    conn.commit()

    return jsonify({'message': '操作成功'})

@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    global account
    data = request.json
    facility = data['facility']
    facility = facility.split('\n')[0]
    time = data['time']
    dateindex = data['dateindex']

    # 更新 UserBookings 表
    cursor = conn.cursor()
    cursor.execute("UPDATE UserBookings SET Status = '已取消' WHERE Username = ? AND Facility = ? AND TimeSlot = ? AND dateindex = ?", (account, facility, time, dateindex))

    # 更新 FacilityBooking 表，增加可用名额
    cursor.execute("UPDATE FacilityBooking SET AvailableSpots = AvailableSpots + 1 WHERE Facility = ? AND TimeSlot = ? AND dateindex = ?", (facility, time, dateindex))
    conn.commit()

    return jsonify({'message': '预约已取消'})


@app.route('/appointments', methods=['GET', 'POST'])
def manage_appointments():
    if request.method == 'POST':
        # 从 dashboard.html 接收并保存预约信息
        appointment_data = request.json
        appointments.append(appointment_data)
        return jsonify(appointment_data), 201
    else:
        # 向 payment.html 提供最新的预约信息
        latest_appointment = appointments[-1] if appointments else {}
        return jsonify(latest_appointment)


@app.route('/reset-availability', methods=['POST'])
def reset_availability():
    try:
        cursor = conn.cursor()
        # 更新 FacilityBooking 表
        cursor.execute("UPDATE FacilityBooking SET AvailableSpots = 100")

        # 清空 UserBookings 表
        cursor.execute("DELETE FROM UserBookings")

        conn.commit()  # 提交更改
        return jsonify({'message': '所有名额已重置为100，用户预约信息已清空'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-day', methods=['GET'])
def get_day():
    return jsonify({'day': day})


@app.route('/get-username')
def get_username():
    return jsonify(username=account)


@app.route('/personal-stats', methods=['GET'])
def personal_stats():
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Location, COUNT(*) as Count 
        FROM UserSchedule 
        WHERE Users = ?
        GROUP BY Location
    """, account)
    records = cursor.fetchall()
    print(records)
    # 构建数据以发送给前端
    labels = [record[0] for record in records]  # 地点
    data = [record[1] for record in records]    #
    print(labels)
    print(data)
    cursor.close()
    return jsonify({'labels': labels, 'data': data})

@app.route('/get-user-schedule-stats', methods=['GET'])
def getUserScheduleStats():
    global account
    location_param = request.args.get('location')
    cursor = conn.cursor()
    cursor.execute("SELECT Time FROM UserSchedule WHERE Users = ? AND Location = ?", account,location_param)
    user_schedule = cursor.fetchall()
    print(user_schedule)
    print(account)
    if user_schedule:
        time = user_schedule[0][0]
        cursor.execute("SELECT Users FROM UserSchedule WHERE Location = ? AND Time = ? AND Users != ?", location_param, time, account)
        similar_schedules = cursor.fetchall()
        print(similar_schedules)

        user_counts = {}
        for schedule in similar_schedules:
            user = schedule[0]
            if user in user_counts:
                user_counts[user] += 1
            else:
                user_counts[user] = 1

        labels = list(user_counts.keys())
        data = list(user_counts.values())
        print(data)
        print(labels)

        return jsonify({'labels': labels, 'data': data})
    return jsonify({'message': 'No data available'})


@app.route('/get-comments', methods=['GET'])
def get_comments():
    page = request.args.get('page', 1, type=int)  # 获取页码，默认为第一页
    per_page = 10  # 每页显示的评论数量

    cursor = conn.cursor()

    # 计算跳过的记录数
    offset = (page - 1) * per_page

    # 修改 SQL 查询以支持分页
    cursor.execute("SELECT Users, Comment FROM Comment ORDER BY [index] desc OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                   (offset, per_page))
    comments = cursor.fetchall()
    print(comments)

    # 将结果转换为 JSON
    return jsonify([{'user': row[0], 'comment': row[1]} for row in comments])


@app.route('/submit-comment', methods=['POST'])
def submit_comment():
    global account
    data = request.json
    comment = data.get('comment')
    user = account  # 使用全局变量 account 作为用户名

    # 插入评论到数据库
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Comment (Users, Comment) VALUES (?, ?)", (user, comment))
    conn.commit()

    return jsonify({'message': '评论成功提交'})

session ={'package':0,'price':0}
@app.route('/set-package', methods=['POST'])
def set_package():
    global session
    data = request.json
    print(data)
    session['package'] = data['package']
    session['price'] = int(data['price'])
    print(session)
    return jsonify({'message': '套餐信息已设置'})

@app.route('/get-package', methods=['GET'])
def get_package():
    return jsonify(session)

@app.route('/get-points', methods=['GET'])
def get_points():
    global account
    cursor = conn.cursor()
    cursor.execute("SELECT point FROM score WHERE Users = ?", account)
    row = cursor.fetchone()
    print(row[0])
    if row:
        return jsonify({'points': row[0]})
    else:
        return jsonify({'points': 0})


@app.route('/confirm-payment', methods=['POST'])
def confirm_payment():
    global account

    # 获取套餐和价格信息
    package = session.get('package')
    price = session.get('price')

    if not package or not price:
        return jsonify({'message': '无效的支付信息'}), 400

    cursor = conn.cursor()

    # 插入套餐信息到 set 表
    cursor.execute("INSERT INTO Setmeal (Users, Setmeal) VALUES (?, ?)", (account, package))

    # 更新用户积分
    cursor.execute("SELECT point FROM score WHERE Users = ?", account)
    result = cursor.fetchone()

    if result:
        current_points = result[0]
        # 确保积分不会变成负数
        new_points = max(current_points - price, 0)
        cursor.execute("UPDATE score SET point = ? WHERE Users = ?", (new_points, account))
    else:
        return jsonify({'message': '积分不足，支付失败'})

    conn.commit()

    return jsonify({'message': '支付成功'})


@app.route('/get-my-package', methods=['GET'])
def get_my_package():
    global account
    cursor = conn.cursor()

    # 从 Setmeal 表中获取当前用户的套餐信息
    cursor.execute("SELECT Setmeal FROM Setmeal WHERE Users = ?", account)
    result = cursor.fetchone()

    if result:
        return jsonify({'setmeal': result[0]})
    else:
        return jsonify({'message': '没有找到套餐信息'})

'''
@app.route('/get-comments', methods=['GET'])
def get_comments():
    cursor = conn.cursor()
    cursor.execute("SELECT Users, Comment FROM Comment")
    comments = cursor.fetchall()
    print(comments)
    return jsonify([{'user': row[0], 'comment': row[1]} for row in comments])
'''

if __name__ == '__main__':
    app.run(debug=True)
