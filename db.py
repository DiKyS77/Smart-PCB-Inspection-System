import mysql.connector
from config import DB_CONFIG

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def get_user(username):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_password(username, new_password):
    import hashlib
    hashed = hashlib.md5(new_password.encode()).hexdigest()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password=%s WHERE username=%s", (hashed, username))
    conn.commit()
    conn.close()