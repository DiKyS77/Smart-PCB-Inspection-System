from flask import Flask, render_template, request, redirect, session, url_for, send_file
from db import get_db, get_user, update_password
import hashlib
import io
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


def ensure_active_column():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN active TINYINT(1) NOT NULL DEFAULT 1')
        conn.commit()
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()


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
        try:
            cursor.execute(
                "SELECT * FROM users WHERE id=%s AND password=%s AND active=1",
                (user_id, hashed)
            )
        except Exception:
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


@app.route('/admin/manage-user', methods=['GET', 'POST'])
def admin_manage_user():
    if session.get('role') != 'admin':
        return redirect('/login')

    error = None
    success = None

    ensure_active_column()
    if request.method == 'POST':
            action = request.form.get('action', 'add')
            user_id = request.form.get('user_id', '').strip()
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')

            if action == 'edit':
                if not user_id or not user_id.isdigit():
                    error = 'ID hanya boleh berisi angka.'
                elif not username:
                    error = 'Username tidak boleh kosong.'
                elif password and password != confirm_password:
                    error = 'Password dan konfirmasi tidak cocok.'
                elif password and (not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password)):
                    error = 'Password harus berisi huruf dan angka.'
                else:
                    conn = get_db()
                    cursor = conn.cursor()
                    try:
                        if password:
                            hashed = hashlib.md5(password.encode()).hexdigest()
                            cursor.execute(
                                'UPDATE users SET username = %s, password = %s WHERE id = %s',
                                (username, hashed, user_id)
                            )
                        else:
                            cursor.execute(
                                'UPDATE users SET username = %s WHERE id = %s',
                                (username, user_id)
                            )
                        conn.commit()
                        success = 'Karyawan berhasil diperbarui.'
                    except Exception:
                        conn.rollback()
                        error = 'Terjadi kesalahan saat memperbarui karyawan.'
                    finally:
                        cursor.close()
                        conn.close()
            elif action in ['deactivate', 'activate']:
                if not user_id or not user_id.isdigit():
                    error = 'ID hanya boleh berisi angka.'
                else:
                    active_value = 0 if action == 'deactivate' else 1
                    conn = get_db()
                    cursor = conn.cursor()
                    try:
                        cursor.execute('UPDATE users SET active = %s WHERE id = %s', (active_value, user_id))
                        conn.commit()
                        if action == 'deactivate':
                            success = 'Karyawan berhasil dinonaktifkan.'
                        else:
                            success = 'Karyawan berhasil diaktifkan kembali.'
                    except Exception:
                        conn.rollback()
                        error = 'Terjadi kesalahan saat mengubah status karyawan.'
                    finally:
                        cursor.close()
                        conn.close()
            else:
                if not user_id or not user_id.isdigit():
                    error = 'ID hanya boleh berisi angka.'
                elif not username:
                    error = 'Username tidak boleh kosong.'
                elif not password or not confirm_password:
                    error = 'Password dan konfirmasi wajib diisi.'
                elif password != confirm_password:
                    error = 'Password dan konfirmasi tidak cocok.'
                elif not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
                    error = 'Password harus berisi huruf dan angka.'
                else:
                    hashed = hashlib.md5(password.encode()).hexdigest()
                    conn = get_db()
                    cursor = conn.cursor()
                    try:
                        cursor.execute(
                            'INSERT INTO users (id, username, password, role, active) VALUES (%s, %s, %s, %s, %s)',
                            (user_id, username, hashed, 'technician', 1)
                        )
                        conn.commit()
                        success = 'Karyawan berhasil ditambahkan.'
                    except Exception as e:
                        conn.rollback()
                        if 'Duplicate' in str(e) or 'duplicate' in str(e).lower():
                            error = 'ID sudah ada. Gunakan ID lain.'
                        else:
                            error = 'Terjadi kesalahan saat menambahkan karyawan.'
                    finally:
                        cursor.close()
                        conn.close()
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, username, role, active FROM users ORDER BY id ASC')
        users = cursor.fetchall()
    except Exception:
        cursor.execute('SELECT id, username, role FROM users ORDER BY id ASC')
        users = cursor.fetchall()
        for user in users:
            user['role'] = user.get('role', 'technician')
            user['active'] = 1
    finally:
        cursor.close()
        conn.close()

    return render_template('admin/manage_user.html', users=users, error=error, success=success)


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


@app.route('/technician/report', methods=['GET', 'POST'])
def technician_report():
    if session.get('role') != 'technician':
        return redirect('/login')

    selected_period = ''
    selected_date = ''
    error = None

    if request.method == 'POST':
        selected_period = request.form.get('period', '').strip()
        selected_date = request.form.get('date', '').strip()

        if not selected_period:
            error = 'Silakan pilih periode terlebih dahulu'
        elif not selected_date:
            error = 'Silakan pilih tanggal terlebih dahulu'

        if error:
            return render_template(
                'technician/report.html',
                error=error,
                selected_period=selected_period,
                selected_date=selected_date
            )

        report_content = (
            f"PDF atau CSV Report\nPeriode: {selected_period or 'N/A'}\n"
            f"Tanggal: {selected_date or 'N/A'}\n"
            "Laporan deteksi PCB berhasil dibuat."
        ).encode('utf-8')
        report_file = io.BytesIO(report_content)
        report_file.seek(0)

        return send_file(
            report_file,
            as_attachment=True,
            download_name='laporan_pcb.txt',
            mimetype='text/plain'
        )

    return render_template(
        'technician/report.html',
        selected_period=selected_period,
        selected_date=selected_date,
        error=error
    )

@app.route('/technician/settings')
def technician_settings():
    if session.get('role') == 'technician':
        return render_template('technician/settings.html')
    return redirect('/login')

@app.route('/change-password', methods=['POST'])
def change_password():
    old = request.form['old_password']
    new = request.form['new_password']

    user = session['username']

    # ambil password lama dari database
    db_user = get_user(user)

    if db_user['password'] != hashlib.md5(old.encode()).hexdigest():
        return render_template('technician/settings.html', error="Password lama salah!")

    update_password(user, new)

    return redirect('/technician')

# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)