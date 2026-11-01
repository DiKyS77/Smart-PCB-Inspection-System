import hashlib

import mysql.connector
from config import DB_CONFIG


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


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
    hashed = hash_password(new_password)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password=%s WHERE username=%s", (hashed, username))
    conn.commit()
    conn.close()
