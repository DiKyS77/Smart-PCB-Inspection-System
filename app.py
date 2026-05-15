from flask import Flask, render_template, request, redirect, session, url_for, send_file
from db import get_db, get_user, update_password
import hashlib
import io
import os
import csv
from openpyxl import Workbook
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'secret123'

# ================= CONFIG UPLOAD =================
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
DEFECT_TYPES = ['spurious_copper', 'spur', 'mouse_bite', 'missing_hole', 'short', 'open_circuit']

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# ensure folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ================= HELPER =================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_image_url(image_path):
    if not image_path:
        return ''
    filename = os.path.basename(image_path)
    return url_for('static', filename=f'uploads/{filename}')


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


def ensure_detections_table():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detections (
                id INT AUTO_INCREMENT PRIMARY KEY,
                technician_id INT,
                image_path VARCHAR(255),
                defect_type VARCHAR(100),
                accuracy DECIMAL(5,2),
                status VARCHAR(50),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()


@app.context_processor
def inject_user():
    return dict(
        user_id=session.get('user_id'),
        username=session.get('username'),
        role=session.get('role')
    )


@app.errorhandler(413)
def request_entity_too_large(error):
    return render_template('technician/detection.html', error='File size must be 5MB or less.'), 413


# ================= LANDING PAGE =================
@app.route('/')
def index():
    return render_template('index.html')


# ================= LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']

        hashed = hashlib.md5(password.encode()).hexdigest()

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM users WHERE (id=%s OR username=%s) AND password=%s AND active=1",
                (identifier, identifier, hashed)
            )
        except Exception:
            cursor.execute(
                "SELECT * FROM users WHERE (id=%s OR username=%s) AND password=%s",
                (identifier, identifier, hashed)
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
            return render_template('auth/login.html', error="Incorrect ID or password.")

    return render_template('auth/login.html')


# ================= ADMIN =================
@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/login')

    ensure_active_column()
    ensure_detections_table()

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    total_detections = 0
    total_technicians = 0
    active_technicians = 0
    top_defect = 'N/A'
    daily_labels = []
    daily_values = []
    defect_labels = []
    defect_values = []
    top_technicians = []
    recent_history = []

    try:
        cursor.execute('SELECT COUNT(*) AS total FROM detections')
        total_detections = cursor.fetchone().get('total', 0) or 0

        cursor.execute('SELECT COUNT(*) AS total FROM users WHERE role=%s', ('technician',))
        total_technicians = cursor.fetchone().get('total', 0) or 0

        cursor.execute('SELECT COUNT(*) AS total FROM users WHERE role=%s AND active=1', ('technician',))
        active_technicians = cursor.fetchone().get('total', 0) or 0

        cursor.execute('SELECT defect_type, COUNT(*) AS count FROM detections GROUP BY defect_type ORDER BY count DESC LIMIT 1')
        row = cursor.fetchone()
        if row:
            top_defect = row.get('defect_type') or 'N/A'

        cursor.execute('SELECT DATE(created_at) AS day, COUNT(*) AS count FROM detections GROUP BY DATE(created_at) ORDER BY day ASC')
        daily_data = cursor.fetchall()
        daily_labels = [str(r['day']) for r in daily_data]
        daily_values = [int(r['count']) for r in daily_data]

        cursor.execute('SELECT defect_type, COUNT(*) AS count FROM detections GROUP BY defect_type ORDER BY count DESC')
        defect_data = cursor.fetchall()
        defect_labels = [r['defect_type'] for r in defect_data]
        defect_values = [int(r['count']) for r in defect_data]

        cursor.execute(
            'SELECT u.username, COUNT(d.id) AS total_detections FROM users u LEFT JOIN detections d ON u.id = d.technician_id WHERE u.role=%s GROUP BY u.id ORDER BY total_detections DESC LIMIT 5',
            ('technician',)
        )
        top_technicians = cursor.fetchall()

        cursor.execute('''SELECT d.id, d.image_path, d.defect_type, d.accuracy, d.status, d.created_at, u.username
                          FROM detections d
                          LEFT JOIN users u ON u.id = d.technician_id
                          ORDER BY d.created_at DESC LIMIT 6''')
        recent_history = cursor.fetchall()
        for row in recent_history:
            row['image_url'] = get_image_url(row['image_path'])
            row['file_name'] = os.path.basename(row['image_path']) if row['image_path'] else ''
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'admin/dashboard.html',
        total_detections=total_detections,
        total_technicians=total_technicians,
        active_technicians=active_technicians,
        top_defect=top_defect,
        daily_labels=daily_labels,
        daily_values=daily_values,
        defect_labels=defect_labels,
        defect_values=defect_values,
        top_technicians=top_technicians,
        recent_history=recent_history,
        username=session.get('username'),
        role=session.get('role')
    )


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
                    error = 'ID must be numeric.'
                elif not username:
                    error = 'Username cannot be empty.'
                elif password and password != confirm_password:
                    error = 'Password and confirmation do not match.'
                elif password and (not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password)):
                    error = 'Password must contain letters and numbers.'
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
                        success = 'Technician updated successfully.'
                    except Exception:
                        conn.rollback()
                        error = 'An error occurred while updating the technician.'
                    finally:
                        cursor.close()
                        conn.close()
            elif action in ['deactivate', 'activate', 'delete']:
                if not user_id or not user_id.isdigit():
                    error = 'ID must be numeric.'
                elif action == 'delete' and str(session.get('user_id')) == user_id:
                    error = 'You cannot delete the currently signed-in account.'
                else:
                    conn = get_db()
                    cursor = conn.cursor()
                    try:
                        if action == 'delete':
                            cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
                            success = 'Technician deleted successfully.'
                        else:
                            active_value = 0 if action == 'deactivate' else 1
                            cursor.execute('UPDATE users SET active = %s WHERE id = %s', (active_value, user_id))
                            if action == 'deactivate':
                                success = 'Technician deactivated successfully.'
                            else:
                                success = 'Technician reactivated successfully.'
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        error = 'An error occurred while changing the technician status.'
                    finally:
                        cursor.close()
                        conn.close()
            else:
                if not user_id or not user_id.isdigit():
                    error = 'ID must be numeric.'
                elif not username:
                    error = 'Username cannot be empty.'
                elif not password or not confirm_password:
                    error = 'Password and confirmation are required.'
                elif password != confirm_password:
                    error = 'Password and confirmation do not match.'
                elif not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
                    error = 'Password must contain letters and numbers.'
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
                        success = 'Technician added successfully.'
                    except Exception as e:
                        conn.rollback()
                        if 'Duplicate' in str(e) or 'duplicate' in str(e).lower():
                            error = 'ID already exists. Use another ID.'
                        else:
                            error = 'An error occurred while adding the technician.'
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


@app.route('/admin/report', methods=['GET', 'POST'])
def admin_report():
    if session.get('role') != 'admin':
        return redirect('/login')

    ensure_active_column()
    ensure_detections_table()

    if request.method == 'POST':
        selected_period = request.form.get('period', '').strip()
        selected_date = request.form.get('date', '').strip()
    else:
        selected_period = request.args.get('period', '').strip()
        selected_date = request.args.get('date', '').strip()

    def build_filter_clause(period, date_str):
        clause = ''
        params = []
        if period and date_str:
            if period == 'weekly':
                clause = ' AND YEARWEEK(d.created_at, 1) = YEARWEEK(%s, 1)'
                params = [date_str]
            elif period == 'monthly':
                clause = ' AND YEAR(d.created_at) = YEAR(%s) AND MONTH(d.created_at) = MONTH(%s)'
                params = [date_str, date_str]
            elif period == 'yearly':
                clause = ' AND YEAR(d.created_at) = YEAR(%s)'
                params = [date_str]
        return clause, params

    filter_clause, filter_params = build_filter_clause(selected_period, selected_date)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    total_detections = 0
    total_technicians = 0
    active_technicians = 0
    top_defect = 'N/A'
    daily_labels = []
    daily_values = []
    defect_labels = []
    defect_values = []
    recent_history = []

    try:
        cursor.execute('SELECT COUNT(*) AS total FROM detections d WHERE 1=1' + filter_clause, tuple(filter_params))
        total_detections = cursor.fetchone().get('total', 0) or 0

        try:
            cursor.execute('SELECT COUNT(*) AS total FROM users WHERE role=%s', ('technician',))
            total_technicians = cursor.fetchone().get('total', 0) or 0
        except Exception:
            cursor.execute('SELECT COUNT(*) AS total FROM users')
            total_technicians = cursor.fetchone().get('total', 0) or 0

        try:
            cursor.execute('SELECT COUNT(*) AS total FROM users WHERE role=%s AND active=1', ('technician',))
            active_technicians = cursor.fetchone().get('total', 0) or 0
        except Exception:
            cursor.execute('SELECT COUNT(*) AS total FROM users WHERE active=1')
            active_technicians = cursor.fetchone().get('total', 0) or 0

        cursor.execute('SELECT d.defect_type, COUNT(*) AS count FROM detections d WHERE 1=1' + filter_clause + ' GROUP BY d.defect_type ORDER BY count DESC LIMIT 1', tuple(filter_params))
        row = cursor.fetchone()
        if row:
            top_defect = row.get('defect_type', 'N/A') or 'N/A'

        cursor.execute('SELECT DATE(d.created_at) AS day, COUNT(*) AS count FROM detections d WHERE 1=1' + filter_clause + ' GROUP BY DATE(d.created_at) ORDER BY day ASC', tuple(filter_params))
        daily_data = cursor.fetchall()
        daily_labels = [str(r['day']) for r in daily_data]
        daily_values = [int(r['count']) for r in daily_data]

        cursor.execute('SELECT defect_type, COUNT(*) AS count FROM detections d WHERE 1=1' + filter_clause + ' GROUP BY defect_type ORDER BY count DESC', tuple(filter_params))
        defect_data = cursor.fetchall()
        defect_labels = [r['defect_type'] for r in defect_data]
        defect_values = [int(r['count']) for r in defect_data]

        cursor.execute('''SELECT d.id, d.image_path, d.defect_type, d.accuracy, d.status, d.created_at, u.username
                        FROM detections d
                        LEFT JOIN users u ON u.id = d.technician_id
                        WHERE 1=1''' + filter_clause + ' ORDER BY d.created_at DESC LIMIT 15', tuple(filter_params))
        recent_history = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if request.method == 'POST':
        report_filename = 'detection_report.csv'
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Technician', 'Defect Type', 'Accuracy', 'Status', 'Date', 'Image'])

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''SELECT d.id, d.image_path, d.defect_type, d.accuracy, d.status, d.created_at, u.username
                              FROM detections d
                              LEFT JOIN users u ON u.id = d.technician_id
                              WHERE 1=1''' + filter_clause + ' ORDER BY d.created_at DESC', tuple(filter_params))
            download_rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        for row in download_rows:
            writer.writerow([
                row.get('id'),
                row.get('username') or 'Unknown',
                row.get('defect_type'),
                row.get('accuracy'),
                row.get('status'),
                row.get('created_at'),
                row.get('image_path')
            ])

        buffer = io.BytesIO(output.getvalue().encode('utf-8'))
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=report_filename,
            mimetype='text/csv'
        )

    return render_template(
        'admin/report.html',
        total_detections=total_detections,
        total_technicians=total_technicians,
        active_technicians=active_technicians,
        top_defect=top_defect,
        daily_labels=daily_labels,
        daily_values=daily_values,
        defect_labels=defect_labels,
        defect_values=defect_values,
        recent_history=recent_history,
        selected_period=selected_period,
        selected_date=selected_date
    )


# ================= TECHNICIAN =================
@app.route('/technician')
def technician_dashboard():
    if session.get('role') != 'technician':
        return redirect('/login')

    ensure_detections_table()
    technician_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    total_detections = 0
    avg_accuracy = 0
    top_defect = 'N/A'
    defect_labels = []
    defect_values = []
    defect_summary = []
    recent_detections = []

    try:
        cursor.execute(
            'SELECT COUNT(*) AS total, AVG(accuracy) AS avg_accuracy FROM detections WHERE technician_id = %s',
            (technician_id,)
        )
        row = cursor.fetchone()
        total_detections = row.get('total', 0) or 0
        avg_accuracy = round(row.get('avg_accuracy') or 0, 2)

        cursor.execute(
            'SELECT defect_type, COUNT(*) AS count FROM detections WHERE technician_id = %s GROUP BY defect_type ORDER BY count DESC',
            (technician_id,)
        )
        defect_rows = cursor.fetchall()

        counts = {r['defect_type']: int(r['count']) for r in defect_rows}
        defect_labels = [r['defect_type'] for r in defect_rows]
        defect_values = [int(r['count']) for r in defect_rows]
        if defect_rows:
            top_defect = defect_rows[0]['defect_type']

        for defect in DEFECT_TYPES:
            count = counts.get(defect, 0)
            percent = round((count / total_detections * 100), 2) if total_detections else 0
            defect_summary.append({
                'defect_type': defect,
                'count': count,
                'percent': percent,
                'badge': 'badge-soft-red' if defect == 'spurious_copper' else 'badge-soft-blue'
            })

        cursor.execute(
            'SELECT id, image_path, defect_type, accuracy, status, created_at FROM detections WHERE technician_id = %s ORDER BY created_at DESC LIMIT 6',
            (technician_id,)
        )
        recent_detections = cursor.fetchall()
        for row in recent_detections:
            row['image_url'] = get_image_url(row['image_path'])
            row['file_name'] = os.path.basename(row['image_path']) if row['image_path'] else ''
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'technician/dashboard.html',
        total_detections=total_detections,
        avg_accuracy=avg_accuracy,
        top_defect=top_defect,
        defect_labels=defect_labels,
        defect_values=defect_values,
        defect_summary=defect_summary,
        recent_detections=recent_detections
    )


@app.route('/technician/detection')
def technician_detection():
    if session.get('role') == 'technician':
        return render_template('technician/detection.html')
    return redirect('/login')


# ================= 🔥 DETECTION (UPLOAD + RESULTS) =================
@app.route('/detect', methods=['POST'])
def detect():
    if session.get('role') != 'technician':
        return redirect('/login')

    file = request.files.get('image')

    if file and allowed_file(file.filename):
        ensure_detections_table()

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        image_url = f"/static/uploads/{filename}"

        # ================= AI MODEL (Sementara Dummy) =================
        result = "missing_hole"
        accuracy = 96.42
        status = "DEFECT"

        technician_id = session.get('user_id')
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO detections (technician_id, image_path, defect_type, accuracy, status) VALUES (%s, %s, %s, %s, %s)',
                (technician_id, image_url, result, accuracy, status)
            )
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        return render_template(
            'technician/detection.html',
            image=image_url,
            result=result,
            accuracy=accuracy,
            status=status
        )

    return redirect('/technician/detection')


@app.route('/technician/history')
def technician_history():
    if session.get('role') != 'technician':
        return redirect('/login')

    ensure_detections_table()
    technician_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    history_rows = []

    try:
        cursor.execute(
            'SELECT id, image_path, defect_type, accuracy, status, created_at FROM detections WHERE technician_id = %s ORDER BY created_at DESC',
            (technician_id,)
        )
        history_rows = cursor.fetchall()
        for row in history_rows:
            row['image_url'] = get_image_url(row['image_path'])
            row['file_name'] = os.path.basename(row['image_path']) if row['image_path'] else ''
    finally:
        cursor.close()
        conn.close()

    return render_template('technician/history.html', history_rows=history_rows)


@app.route('/technician/history/<int:detection_id>')
def technician_history_detail(detection_id):
    if session.get('role') != 'technician':
        return redirect('/login')

    ensure_detections_table()
    technician_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            'SELECT id, image_path, defect_type, accuracy, status, created_at FROM detections WHERE id = %s AND technician_id = %s',
            (detection_id, technician_id)
        )
        detection = cursor.fetchone()
        if not detection:
            return redirect(url_for('technician_history'))
        detection['image_url'] = get_image_url(detection['image_path'])
        detection['file_name'] = os.path.basename(detection['image_path']) if detection['image_path'] else ''
    finally:
        cursor.close()
        conn.close()

    return render_template('technician/detail.html', detection=detection)


@app.route('/technician/report', methods=['GET', 'POST'])
def technician_report():
    if session.get('role') != 'technician':
        return redirect('/login')

    ensure_detections_table()
    technician_id = session.get('user_id')
    selected_period = ''
    selected_date = ''
    error = None
    report_rows = []
    total_count = 0
    defect_counts = {d: 0 for d in DEFECT_TYPES}
    defect_labels = []
    defect_values = []
    report_total = 0

    def build_query(period, date_str):
        base = 'SELECT id, image_path, defect_type, accuracy, status, created_at FROM detections WHERE technician_id = %s'
        if not period or not date_str:
            return base + ' ORDER BY created_at DESC', (technician_id,)
        if period == 'weekly':
            return base + ' AND YEARWEEK(created_at, 1) = YEARWEEK(%s, 1) ORDER BY created_at DESC', (technician_id, date_str)
        if period == 'monthly':
            return base + ' AND YEAR(created_at) = YEAR(%s) AND MONTH(created_at) = MONTH(%s) ORDER BY created_at DESC', (technician_id, date_str, date_str)
        if period == 'yearly':
            return base + ' AND YEAR(created_at) = YEAR(%s) ORDER BY created_at DESC', (technician_id, date_str)
        return base + ' ORDER BY created_at DESC', (technician_id,)

    if request.method == 'POST':
        selected_period = request.form.get('period', '').strip()
        selected_date = request.form.get('date', '').strip()

        if not selected_period:
            error = 'Please select a period first'
        elif not selected_date:
            error = 'Please select a date first'

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        query, params = build_query(selected_period, selected_date)
        cursor.execute(query, params)
        report_rows = cursor.fetchall()

        total_count = len(report_rows)
        for row in report_rows:
            defect_counts[row['defect_type']] = defect_counts.get(row['defect_type'], 0) + 1
            row['image_url'] = get_image_url(row['image_path'])
            row['file_name'] = os.path.basename(row['image_path']) if row['image_path'] else ''

        defect_labels = [d for d in DEFECT_TYPES if defect_counts[d] > 0]
        defect_values = [defect_counts[d] for d in DEFECT_TYPES if defect_counts[d] > 0]
        report_total = total_count

        if request.method == 'POST' and not error:
            report_filename = 'technician_report.xlsx'
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = 'Report'
            worksheet.append(['ID', 'Defect Type', 'Accuracy', 'Status', 'Date', 'File Name'])
            for row in report_rows:
                worksheet.append([
                    row['id'],
                    row['defect_type'],
                    row['accuracy'],
                    row['status'],
                    row['created_at'],
                    os.path.basename(row['image_path'])
                ])
            buffer = io.BytesIO()
            workbook.save(buffer)
            buffer.seek(0)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=report_filename,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
    finally:
        cursor.close()
        conn.close()

    defect_summary = []
    for defect in DEFECT_TYPES:
        count = defect_counts.get(defect, 0)
        percent = round((count / total_count * 100), 2) if total_count else 0
        defect_summary.append({
            'defect_type': defect,
            'count': count,
            'percent': percent,
            'badge_color': 'danger' if defect == 'spurious_copper' else 'primary'
        })

    return render_template(
        'technician/report.html',
        selected_period=selected_period,
        selected_date=selected_date,
        error=error,
        report_rows=report_rows,
        report_total=report_total,
        defect_summary=defect_summary,
        defect_labels=defect_labels,
        defect_values=defect_values
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

    # get old password from database
    db_user = get_user(user)

    if db_user['password'] != hashlib.md5(old.encode()).hexdigest():
        return render_template('technician/settings.html', error="Old password is incorrect!")

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