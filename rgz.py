from flask import Blueprint, render_template, request, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from os import path
import re

rgz = Blueprint('rgz', __name__)

DB_NAME = 'rgz_storage.db'

USERNAME_RE = re.compile(r'^[A-Za-z0-9_.!,?\-]{3,30}$')
PASSWORD_RE = re.compile(r'^[A-Za-z0-9_.!,?\-]{6,50}$')


def db_connect():
    folder = path.dirname(path.realpath(__file__))
    db_path = path.join(folder, DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    return conn, cur


def db_close(conn, cur):
    conn.commit()
    cur.close()
    conn.close()


def init_db():
    conn, cur = db_connect()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rgz_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rgz_lockers (
            id INTEGER PRIMARY KEY,
            owner_id INTEGER,
            FOREIGN KEY (owner_id) REFERENCES rgz_users(id)
        );
    """)

    cur.execute("SELECT COUNT(*) AS c FROM rgz_lockers;")
    count = cur.fetchone()['c']
    if count < 100:
        cur.execute("DELETE FROM rgz_lockers;")
        for i in range(1, 101):
            cur.execute("INSERT INTO rgz_lockers(id, owner_id) VALUES (?, NULL);", (i,))

    # создаём администратора
    cur.execute("SELECT id FROM rgz_users WHERE login = 'admin';")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO rgz_users(login, password, is_admin) VALUES (?, ?, 1);",
            ('admin', generate_password_hash('admin123'))
        )

    db_close(conn, cur)


init_db()

def current_user():
    uid = session.get('rgz_user_id')
    login = session.get('rgz_login')
    if not (uid and login):
        return None
    
    conn, cur = db_connect()
    cur.execute("SELECT is_admin FROM rgz_users WHERE id=?;", (uid,))
    row = cur.fetchone()
    db_close(conn, cur)

    if not row:
        return None

    return {
        'id': uid,
        'login': login,
        'is_admin': (row['is_admin'] == 1)
    }

def jsonrpc_error(code, msg, _id):
    return {"jsonrpc": "2.0", "error": {"code": code, "message": msg}, "id": _id}


def jsonrpc_result(result, _id):
    return {"jsonrpc": "2.0", "result": result, "id": _id}


@rgz.route('/rgz/')
def rgz_index():
    return render_template('rgz/rgz.html')


@rgz.route('/rgz/register', methods=['GET', 'POST'])
def rgz_register():
    if request.method == 'GET':
        return render_template('rgz/register.html')

    login = request.form.get('login', '').strip()
    password = request.form.get('password', '')

    if not USERNAME_RE.match(login):
        return render_template('rgz/register.html',
                               error="Логин должен состоять из латинских букв, цифр и символов _.!,?- , длина 3–30.",
                               login=login)

    if not PASSWORD_RE.match(password):
        return render_template('rgz/register.html',
                               error="Пароль должен состоять из латинских букв, цифр и символов _.!,?- , длина 6–50.",
                               login=login)

    conn, cur = db_connect()
    cur.execute("SELECT id FROM rgz_users WHERE login=?;", (login,))
    if cur.fetchone():
        db_close(conn, cur)
        return render_template('rgz/register.html', error="Пользователь уже существует", login=login)

    pwd_hash = generate_password_hash(password)
    cur.execute("INSERT INTO rgz_users(login, password) VALUES (?, ?);", (login, pwd_hash))
    uid = cur.lastrowid
    db_close(conn, cur)

    session['rgz_user_id'] = uid
    session['rgz_login'] = login

    return render_template('rgz/register.html', success="Регистрация успешна!", login=login)


@rgz.route('/rgz/login', methods=['GET', 'POST'])
def rgz_login():
    if request.method == 'GET':
        return render_template('rgz/login.html')

    login = request.form.get('login', '').strip()
    password = request.form.get('password', '')

    conn, cur = db_connect()
    cur.execute("SELECT id, login, password FROM rgz_users WHERE login=?;", (login,))
    row = cur.fetchone()
    db_close(conn, cur)

    if not row or not check_password_hash(row['password'], password):
        return render_template('rgz/login.html', error="Неверный логин или пароль", login=login)

    session['rgz_user_id'] = row['id']
    session['rgz_login'] = row['login']

    return redirect('/rgz/')


@rgz.route('/rgz/logout')
def rgz_logout():
    session.pop('rgz_user_id', None)
    session.pop('rgz_login', None)
    return redirect('/rgz/login?logout=1')


@rgz.route('/rgz/delete-account', methods=['POST'])
def rgz_delete_account():
    user = current_user()
    if not user:
        return redirect('/rgz/login')
    
    if user['is_admin']:
        return redirect('/rgz/login?deleted_admin=1')
    
    conn, cur = db_connect()

    cur.execute("UPDATE rgz_lockers SET owner_id=NULL WHERE owner_id=?;", (user['id'],))

    cur.execute("DELETE FROM rgz_users WHERE id=?;", (user['id'],))

    db_close(conn, cur)

    session.pop('rgz_user_id', None)
    session.pop('rgz_login', None)

    return redirect('/rgz/login?deleted=1')


@rgz.route('/rgz/json-rpc-api', methods=['POST'])
def rgz_api():
    data = request.get_json()
    if not data:
        return jsonrpc_error(-32700, "Некорректный JSON", None)

    method = data.get('method')
    params = data.get('params')
    _id = data.get('id')

    user = current_user()

    if method == 'info':
        conn, cur = db_connect()
        cur.execute("""
            SELECT l.id, l.owner_id, u.login AS owner_login
            FROM rgz_lockers l
            LEFT JOIN rgz_users u ON u.id = l.owner_id
            ORDER BY l.id;
        """)
        rows = cur.fetchall()
        db_close(conn, cur)

        total = 100
        occupied = sum(1 for r in rows if r['owner_id'] is not None)
        free = total - occupied
        my_count = 0

        lockers = []
        for r in rows:
            is_free = r['owner_id'] is None
            is_mine = user and r['owner_id'] == user['id']

            if is_mine:
                my_count += 1

            lockers.append({
                "id": r['id'],
                "free": is_free,
                "mine": bool(is_mine),
                "owner": r['owner_login'] if r['owner_login'] else ""
            })

        return jsonrpc_result({
            "user": user,
            "total": total,
            "occupied": occupied,
            "free": free,
            "my_count": my_count,
            "lockers": lockers
        }, _id)

    if not user:
        return jsonrpc_error(1, "Вы не авторизованы", _id)

    if method == 'booking':
        try:
            locker_id = int(params)
        except:
            return jsonrpc_error(2, "Некорректный номер ячейки", _id)

        conn, cur = db_connect()
        cur.execute("SELECT id, owner_id FROM rgz_lockers WHERE id=?;", (locker_id,))
        row = cur.fetchone()
        if not row:
            db_close(conn, cur)
            return jsonrpc_error(5, "Такой ячейки не существует", _id)

        if row['owner_id'] is not None:
            db_close(conn, cur)
            return jsonrpc_error(2, "Ячейка уже занята", _id)
        
        cur.execute("SELECT COUNT(*) AS c FROM rgz_lockers WHERE owner_id=?;", (user['id'],))
        cnt = cur.fetchone()['c']

        if cnt >= 5 and not user['is_admin']:
            db_close(conn, cur)
            return jsonrpc_error(6, "Нельзя бронировать более пяти ячеек", _id)

        cur.execute("UPDATE rgz_lockers SET owner_id=? WHERE id=?;", (user['id'], locker_id))
        db_close(conn, cur)

        return jsonrpc_result({"ok": True}, _id)

    if method == 'cancellation':
        try:
            locker_id = int(params)
        except:
            return jsonrpc_error(2, "Некорректный номер ячейки", _id)

        conn, cur = db_connect()
        cur.execute("SELECT id, owner_id FROM rgz_lockers WHERE id=?;", (locker_id,))
        row = cur.fetchone()

        if not row:
            db_close(conn, cur)
            return jsonrpc_error(5, "Такой ячейки не существует", _id)

        if row['owner_id'] is None:
            db_close(conn, cur)
            return jsonrpc_error(3, "Эта ячейка уже свободна", _id)

        if row['owner_id'] != user['id'] and not user['is_admin']:
            db_close(conn, cur)
            return jsonrpc_error(4, "Нельзя снять бронь с чужой ячейки", _id)

        cur.execute("UPDATE rgz_lockers SET owner_id=NULL WHERE id=?;", (locker_id,))
        db_close(conn, cur)

        return jsonrpc_result({"ok": True}, _id)

    return jsonrpc_error(-32601, "Метод не найден", _id)