from flask import Flask, render_template, request, redirect, session
from db import get_db
import hashlib

app = Flask(__name__)
app.secret_key = 'secret123'

# ================= LOGIN =================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form['id']
        password = request.form['password']

        hashed = hashlib.md5(password.encode()).hexdigest()

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE id=%s AND password=%s",
            (user_id, hashed)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']

            if user['role'] == 'admin':
                return redirect('/admin')
            else:
                return redirect('/karyawan')
        else:
            return render_template('auth/login.html', error="Login gagal")

    return render_template('auth/login.html')


# ================= ADMIN =================
@app.route('/admin')
def admin_dashboard():
    if 'role' in session and session['role'] == 'admin':
        return render_template('admin/dashboard.html')
    return redirect('/')


@app.route('/admin/manage-user')
def admin_manage_user():
    if 'role' in session and session['role'] == 'admin':
        return render_template('admin/manage_user.html')
    return redirect('/')


@app.route('/admin/report')
def admin_report():
    if 'role' in session and session['role'] == 'admin':
        return render_template('admin/report.html')
    return redirect('/')


@app.route('/admin/add-user')
def admin_add_user():
    return render_template('admin/add_user.html')


@app.route('/admin/edit-user/<int:id>')
def admin_edit_user(id):
    return f"Edit user {id}"


@app.route('/admin/delete-user/<int:id>')
def admin_delete_user(id):
    return f"Hapus user {id}"



# ================= KARYAWAN =================
@app.route('/karyawan')
def karyawan_dashboard():
    if 'role' in session and session['role'] == 'karyawan':
        return render_template('karyawan/dashboard.html')
    return redirect('/')


@app.route('/karyawan/detection')
def karyawan_detection():
    if 'role' in session and session['role'] == 'karyawan':
        return render_template('karyawan/detection.html')
    return redirect('/')


@app.route('/karyawan/history')
def karyawan_history():
    if 'role' in session and session['role'] == 'karyawan':
        return render_template('karyawan/history.html')
    return redirect('/')


@app.route('/karyawan/report')
def karyawan_report():
    if 'role' in session and session['role'] == 'karyawan':
        return render_template('karyawan/report.html')
    return redirect('/')


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)