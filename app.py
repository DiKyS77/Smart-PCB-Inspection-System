from flask import Flask, render_template, request, redirect, session, url_for
from db import get_db
import hashlib
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'secret123'

# ================= CONFIG UPLOAD =================
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# pastikan folder ada
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ================= HELPER =================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.context_processor
def inject_user():
    return dict(
        username=session.get('username'),
        role=session.get('role')
    )


# ================= LANDING PAGE =================
@app.route('/')
def index():
    return render_template('index.html')


# ================= LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
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
            session['username'] = user['username']
            session['role'] = user['role']

            if user['role'] == 'admin':
                return redirect('/admin')
            else:
                return redirect('/technician')
        else:
            return render_template('auth/login.html', error="ID atau password salah.")

    return render_template('auth/login.html')


# ================= ADMIN =================
@app.route('/admin')
def admin_dashboard():
    if session.get('role') == 'admin':
        return render_template('admin/dashboard.html')
    return redirect('/login')


@app.route('/admin/manage-user')
def admin_manage_user():
    if session.get('role') == 'admin':
        return render_template('admin/manage_user.html')
    return redirect('/login')


@app.route('/admin/report')
def admin_report():
    if session.get('role') == 'admin':
        return render_template('admin/report.html')
    return redirect('/login')


# ================= TECHNICIAN =================
@app.route('/technician')
def technician_dashboard():
    if session.get('role') == 'technician':
        return render_template('technician/dashboard.html')
    return redirect('/login')


@app.route('/technician/detection')
def technician_detection():
    if session.get('role') == 'technician':
        return render_template('technician/detection.html')
    return redirect('/login')


# ================= 🔥 DETEKSI (UPLOAD + HASIL) =================
@app.route('/detect', methods=['POST'])
def detect():
    if session.get('role') != 'technician':
        return redirect('/login')

    file = request.files.get('image')

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # ================= AI MODEL (Sementara Dummy) =================
        result = "Missing Hole"
        accuracy = 96.42
        status = "CACAT"

        return render_template(
            'technician/detection.html',
            image=filepath,
            result=result,
            accuracy=accuracy,
            status=status
        )

    return redirect('/technician/detection')


@app.route('/technician/history')
def technician_history():
    if session.get('role') == 'technician':
        return render_template('technician/history.html')
    return redirect('/login')


@app.route('/technician/report')
def technician_report():
    if session.get('role') == 'technician':
        return render_template('technician/report.html')
    return redirect('/login')


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)