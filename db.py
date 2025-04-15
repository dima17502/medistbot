import sqlite3
import traceback


def ensure_connection(func):
    def inner(*args, **kwargs):
        with sqlite3.connect('user.db') as conn:
            res = func(*args, conn=conn, **kwargs)
        return res
    return inner


@ensure_connection
def init_db(conn):
    c = conn.cursor()
    c.execute('''
                CREATE TABLE IF NOT EXISTS user_states (
                    user_id             INTEGER NOT NULL PRIMARY KEY,
                    current_article     INTEGER,
                    schema_is_open      INTEGER,
                    answers             TEXT,
                    nav_path            TEXT,
                    last_query          TEXT
                )
    ''')
    c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id             INTEGER NOT NULL PRIMARY KEY,
                    first_name          TEXT,
                    last_name           TEXT,
                    username            TEXT,
                    status              INTEGER NOT NULL
                )
    ''')
    conn.commit()





@ensure_connection
def get_user_state(user_id:int,conn):
    c = conn.cursor()
    c.execute('BEGIN')    
    try:
        c.execute('''SELECT * FROM user_states WHERE user_id = ?''',(user_id,))
        res = c.fetchone()
        return res
    except Exception:
        c.execute('ROLLBACK')
        traceback.print_exc()


@ensure_connection
def get_user_data(user_id:int,conn):
    c = conn.cursor()
    c.execute('BEGIN')
    try:
        c.execute('''SELECT * FROM users WHERE user_id = ?''',(user_id,))
        res = c.fetchone()
        return res
    except Exception:
        c.execute('ROLLBACK')
        traceback.print_exc()



@ensure_connection
def update_user_state(current_article:int,schema_is_open:int, answers:str, nav_path:str,last_query:str,user_id:int,conn):
    c = conn.cursor()
    c.execute('BEGIN')
    try:
        if get_user_state(user_id=user_id) is None:
            c.execute('''INSERT INTO user_states (user_id, current_article, schema_is_open, answers, nav_path,last_query) VALUES (?,?,?,?,?,?)''',(user_id,current_article,schema_is_open,answers,nav_path,last_query))
        else:
            if last_query != '':
                c.execute('''UPDATE user_states SET current_article = ? , schema_is_open = ? , answers = ? , nav_path = ?, last_query = ? WHERE user_id = ?;''',(current_article,schema_is_open,answers,nav_path, last_query, user_id))
            else:
                c.execute('''UPDATE user_states SET current_article = ? , schema_is_open = ? , answers = ? , nav_path = ? WHERE user_id = ?;''',(current_article,schema_is_open,answers,nav_path, user_id))
        c.execute('COMMIT')
    except Exception:
        c.execute('ROLLBACK')
        traceback.print_exc()


@ensure_connection
def update_user_data(first_name:str, last_name:str, username:str, user_id:int, status:int, conn):
    c = conn.cursor()
    c.execute('BEGIN')
    try:
        if get_user_data(user_id=user_id) is None:
            c.execute('''INSERT INTO users (user_id, first_name, last_name, username, status) VALUES (?,?,?,?,?)''',(user_id,first_name,last_name,username,status))
        else:
            c.execute('''UPDATE users SET first_name = ? , last_name = ? , username = ?, status = ? WHERE user_id = ?;''',(first_name,last_name,username,status,user_id))
        c.execute('COMMIT')
    except Exception:
        c.execute('ROLLBACK')
        traceback.print_exc()

@ensure_connection
def update_users_status(status:int,users:list,conn):
    c = conn.cursor()
    t_users = tuple(users)
    c.execute('BEGIN')
    try:
        for u_id in users:
            c.execute('''UPDATE users SET status = ? WHERE user_id = ?;''',(status,u_id))
        c.execute('COMMIT')
    except Exception:
        c.execute('ROLLBACK')
        traceback.print_exc()


@ensure_connection
def insert(current_article:int,schema_is_open:int, answers:str, nav_path:str,user_id:int,conn):
    c = conn.cursor()
    c.execute('BEGIN')

    try:
        c.execute('''INSERT INTO user_states (user_id, current_article, schema_is_open, answers, nav_path) VALUES (?,?,?,?,?)''',(user_id,current_article,schema_is_open,answers,nav_path))
        c.execute('COMMIT')
    except Exception:
        c.execute('ROLLBACK')
        traceback.print_exc()


@ensure_connection
def get_available_users(conn):
    c = conn.cursor()
    try:
        c.execute('''SELECT * FROM users WHERE status = ?''',(1,))
        res = c.fetchall()
        return res
    except Exception:
        c.execute('ROLLBACK')
        traceback.print_exc()
    

'''
init_db()
for i in range(1000000):
    insert(57,1,'ynynn','12',i)

import time
t0 = time.time()
d = {}
for i in range(10000000):
    d[i] = str(i)
print(time.time() - t0)

'''