"""
Smart PCB Inspection System — Flask Application
================================================
Roles  : admin, technician
Model  : YOLOv8 (best.pt)
DB     : MySQL (via db.get_db())
"""

import csv
import hashlib
import io
import os
import time
from typing import Optional

import cv2
import matplotlib
matplotlib.use('Agg')          # non-interactive backend — wajib di server
import matplotlib.pyplot as plt
from flask import Flask, redirect, render_template, request, send_file, session, url_for
from openpyxl import Workbook
from ultralytics import YOLO
from werkzeug.utils import secure_filename

from db import get_db, get_user, update_password


# ─────────────────────────────────────────────────────────────────────────────
# APP CONFIG
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')

UPLOAD_FOLDER    = 'static/uploads'
RESULT_FOLDER    = 'static/results'
NORMALIZE_FOLDER = 'static/normalize'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

DEFECT_TYPES = [
    'spurious_copper', 'spur', 'mouse_bite',
    'missing_hole', 'short', 'open_circuit',
]

app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024   # 5 MB

for _folder in (UPLOAD_FOLDER, RESULT_FOLDER, NORMALIZE_FOLDER):
    os.makedirs(_folder, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# YOLO MODEL + FEATURE-MAP HOOK
# ─────────────────────────────────────────────────────────────────────────────

model = YOLO('best.pt')

_feature_maps: list = []


def _hook_fn(module, inp, output):
    """Forward hook — captures backbone layer-4 output for feature-map viz."""
    _feature_maps.clear()
    _feature_maps.append(output.detach().cpu())


model.model.model[4].register_forward_hook(_hook_fn)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_image_url(image_path: str) -> str:
    """Convert a stored DB image path to a usable URL.

    The DB stores paths like '/static/results/result_123.jpg'.
    • If the path already starts with '/static/' → return as-is (valid URL).
    • Otherwise fall back to the uploads folder (legacy rows).
    """
    if not image_path:
        return ''
    if image_path.startswith('/static/'):
        return image_path                        # already a valid URL
    # legacy fallback: bare filename stored without /static/ prefix
    return url_for('static', filename=f'uploads/{os.path.basename(image_path)}')


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def unique_filename(original: str) -> str:
    """Prepend a millisecond timestamp to prevent filename collisions."""
    return f'{int(time.time() * 1000)}_{secure_filename(original)}'


def _build_defect_summary(defect_counts: dict, total: int) -> list:
    """Build the per-defect summary list used by dashboard & report pages."""
    summary = []
    for defect in DEFECT_TYPES:
        count   = defect_counts.get(defect, 0)
        percent = round(count / total * 100, 2) if total else 0
        summary.append({
            'defect_type': defect,
            'count':       count,
            'percent':     percent,
            'badge_color': 'danger' if defect == 'spurious_copper' else 'primary',
        })
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE MIGRATIONS  (run once on startup)
# ─────────────────────────────────────────────────────────────────────────────

def _migrate():
    conn   = get_db()
    cursor = conn.cursor()
    try:
        # Add `active` column only if it doesn't exist yet
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'users'
              AND COLUMN_NAME  = 'active'
        """)
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                'ALTER TABLE users ADD COLUMN active TINYINT(1) NOT NULL DEFAULT 1'
            )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                technician_id  INT,
                image_path     VARCHAR(255),
                defect_type    VARCHAR(100),
                accuracy       DECIMAL(5,2),
                status         VARCHAR(50),
                created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    except Exception as exc:
        print(f'[migrate] warning: {exc}')
    finally:
        cursor.close()
        conn.close()


_migrate()


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT PROCESSORS & ERROR HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

@app.context_processor
def _inject_session():
    return dict(
        user_id=session.get('user_id'),
        username=session.get('username'),
        role=session.get('role'),
    )


@app.errorhandler(413)
def _too_large(error):
    return render_template(
        'technician/detection.html',
        error='File size must be 5 MB or less.'
    ), 413


# ─────────────────────────────────────────────────────────────────────────────
# LANDING PAGE
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        hashed     = hash_password(request.form['password'])

        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT * FROM users
                   WHERE (id = %s OR username = %s)
                     AND password = %s
                     AND active   = 1""",
                (identifier, identifier, hashed),
            )
            user = cursor.fetchone()
        except Exception:
            # Fallback for DBs where `active` column doesn't exist yet
            cursor.execute(
                """SELECT * FROM users
                   WHERE (id = %s OR username = %s)
                     AND password = %s""",
                (identifier, identifier, hashed),
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

        if user:
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['role']     = user['role']
            return redirect('/admin' if user['role'] == 'admin' else '/technician')

        return render_template('auth/login.html', error='Incorrect ID or password.')

    return render_template('auth/login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)

    data = dict(
        total_detections=0, total_technicians=0, active_technicians=0,
        top_defect='N/A', daily_labels=[], daily_values=[],
        defect_labels=[], defect_values=[],
        top_technicians=[], recent_history=[],
    )

    try:
        cursor.execute('SELECT COUNT(*) AS total FROM detections')
        data['total_detections'] = cursor.fetchone()['total'] or 0

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'technician'")
        data['total_technicians'] = cursor.fetchone()['total'] or 0

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'technician' AND active = 1")
        data['active_technicians'] = cursor.fetchone()['total'] or 0

        cursor.execute("""
            SELECT defect_type, COUNT(*) AS cnt FROM detections
            GROUP BY defect_type ORDER BY cnt DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            data['top_defect'] = row['defect_type'] or 'N/A'

        cursor.execute("""
            SELECT DATE(created_at) AS day, COUNT(*) AS cnt
            FROM detections GROUP BY day ORDER BY day ASC
        """)
        rows = cursor.fetchall()
        data['daily_labels'] = [str(r['day']) for r in rows]
        data['daily_values'] = [int(r['cnt'])  for r in rows]

        cursor.execute("""
            SELECT defect_type, COUNT(*) AS cnt FROM detections
            GROUP BY defect_type ORDER BY cnt DESC
        """)
        rows = cursor.fetchall()
        data['defect_labels'] = [r['defect_type'] for r in rows]
        data['defect_values'] = [int(r['cnt'])     for r in rows]

        cursor.execute("""
            SELECT u.username, COUNT(d.id) AS total_detections
            FROM users u LEFT JOIN detections d ON u.id = d.technician_id
            WHERE u.role = 'technician'
            GROUP BY u.id ORDER BY total_detections DESC LIMIT 5
        """)
        data['top_technicians'] = cursor.fetchall()

        cursor.execute("""
            SELECT d.id, d.image_path, d.defect_type, d.accuracy,
                   d.status, d.created_at, u.username
            FROM detections d
            LEFT JOIN users u ON u.id = d.technician_id
            ORDER BY d.created_at DESC LIMIT 6
        """)
        recent = cursor.fetchall()
        for row in recent:
            row['image_url'] = get_image_url(row['image_path'])
            row['file_name'] = os.path.basename(row['image_path']) if row['image_path'] else ''
        data['recent_history'] = recent

    finally:
        cursor.close()
        conn.close()

    return render_template('admin/dashboard.html', **data)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — MANAGE USERS
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/admin/manage-user', methods=['GET', 'POST'])
def admin_manage_user():
    if session.get('role') != 'admin':
        return redirect('/login')

    error   = None
    success = None

    if request.method == 'POST':
        action           = request.form.get('action', 'add')
        user_id          = request.form.get('user_id', '').strip()
        username         = request.form.get('username', '').strip()
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        def _bad_id():
            return not user_id or not user_id.isdigit()

        def _pw_mismatch():
            return password and password != confirm_password

        def _pw_weak():
            return not any(c.isalpha() for c in password) or \
                   not any(c.isdigit() for c in password)

        if action == 'edit':
            if _bad_id():
                error = 'ID must be numeric.'
            elif not username:
                error = 'Username cannot be empty.'
            elif _pw_mismatch():
                error = 'Password and confirmation do not match.'
            elif password and _pw_weak():
                error = 'Password must contain letters and numbers.'
            else:
                conn   = get_db()
                cursor = conn.cursor()
                try:
                    if password:
                        cursor.execute(
                            'UPDATE users SET username = %s, password = %s WHERE id = %s',
                            (username, hash_password(password), user_id),
                        )
                    else:
                        cursor.execute(
                            'UPDATE users SET username = %s WHERE id = %s',
                            (username, user_id),
                        )
                    conn.commit()
                    success = 'Technician updated successfully.'
                except Exception:
                    conn.rollback()
                    error = 'An error occurred while updating the technician.'
                finally:
                    cursor.close()
                    conn.close()

        elif action in ('activate', 'deactivate', 'delete'):
            if _bad_id():
                error = 'ID must be numeric.'
            elif action == 'delete' and str(session.get('user_id')) == user_id:
                error = 'You cannot delete your own account.'
            else:
                conn   = get_db()
                cursor = conn.cursor()
                try:
                    if action == 'delete':
                        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
                        success = 'Technician deleted successfully.'
                    else:
                        active_val = 1 if action == 'activate' else 0
                        cursor.execute(
                            'UPDATE users SET active = %s WHERE id = %s',
                            (active_val, user_id),
                        )
                        success = (
                            'Technician reactivated successfully.'
                            if action == 'activate'
                            else 'Technician deactivated successfully.'
                        )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    error = 'An error occurred while updating the technician status.'
                finally:
                    cursor.close()
                    conn.close()

        else:   # add
            if _bad_id():
                error = 'ID must be numeric.'
            elif not username:
                error = 'Username cannot be empty.'
            elif not password or not confirm_password:
                error = 'Password and confirmation are required.'
            elif _pw_mismatch():
                error = 'Password and confirmation do not match.'
            elif _pw_weak():
                error = 'Password must contain letters and numbers.'
            else:
                conn   = get_db()
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        'INSERT INTO users (id, username, password, role, active) VALUES (%s,%s,%s,%s,%s)',
                        (user_id, username, hash_password(password), 'technician', 1),
                    )
                    conn.commit()
                    success = 'Technician added successfully.'
                except Exception as exc:
                    conn.rollback()
                    error = (
                        'ID already exists. Use another ID.'
                        if 'duplicate' in str(exc).lower()
                        else 'An error occurred while adding the technician.'
                    )
                finally:
                    cursor.close()
                    conn.close()

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, username, role, active FROM users ORDER BY id ASC')
        users = cursor.fetchall()
    except Exception:
        cursor.execute('SELECT id, username, role FROM users ORDER BY id ASC')
        users = cursor.fetchall()
        for u in users:
            u.setdefault('active', 1)
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'admin/manage_user.html',
        users=users, error=error, success=success,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — REPORT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/admin/report', methods=['GET', 'POST'])
def admin_report():
    if session.get('role') != 'admin':
        return redirect('/login')

    # FIX: pakai start_date + end_date (range) sesuai form di admin_report.html
    if request.method == 'POST':
        start_date = request.form.get('start_date', '').strip()
        end_date   = request.form.get('end_date',   '').strip()
    else:
        start_date = request.args.get('start_date', '').strip()
        end_date   = request.args.get('end_date',   '').strip()

    # Build dynamic WHERE clause
    filter_sql    = ''
    filter_params: list = []
    if start_date and end_date:
        filter_sql    = ' AND DATE(d.created_at) BETWEEN %s AND %s'
        filter_params = [start_date, end_date]
    elif start_date:
        filter_sql    = ' AND DATE(d.created_at) >= %s'
        filter_params = [start_date]
    elif end_date:
        filter_sql    = ' AND DATE(d.created_at) <= %s'
        filter_params = [end_date]

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)

    data = dict(
        total_detections=0, total_technicians=0, active_technicians=0,
        top_defect='N/A', daily_labels=[], daily_values=[],
        defect_labels=[], defect_values=[],
        recent_history=[],
        start_date=start_date, end_date=end_date,
    )

    try:
        cursor.execute(
            f'SELECT COUNT(*) AS total FROM detections d WHERE 1=1{filter_sql}',
            filter_params,
        )
        data['total_detections'] = cursor.fetchone()['total'] or 0

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'technician'")
        data['total_technicians'] = cursor.fetchone()['total'] or 0

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'technician' AND active = 1")
        data['active_technicians'] = cursor.fetchone()['total'] or 0

        cursor.execute(
            f"""SELECT d.defect_type, COUNT(*) AS cnt FROM detections d
                WHERE 1=1{filter_sql}
                GROUP BY d.defect_type ORDER BY cnt DESC LIMIT 1""",
            filter_params,
        )
        row = cursor.fetchone()
        if row:
            data['top_defect'] = row['defect_type'] or 'N/A'

        cursor.execute(
            f"""SELECT DATE(d.created_at) AS day, COUNT(*) AS cnt
                FROM detections d WHERE 1=1{filter_sql}
                GROUP BY day ORDER BY day ASC""",
            filter_params,
        )
        rows = cursor.fetchall()
        data['daily_labels'] = [str(r['day']) for r in rows]
        data['daily_values'] = [int(r['cnt'])  for r in rows]

        cursor.execute(
            f"""SELECT defect_type, COUNT(*) AS cnt FROM detections d
                WHERE 1=1{filter_sql}
                GROUP BY defect_type ORDER BY cnt DESC""",
            filter_params,
        )
        rows = cursor.fetchall()
        data['defect_labels'] = [r['defect_type'] for r in rows]
        data['defect_values'] = [int(r['cnt'])     for r in rows]

        cursor.execute(
            f"""SELECT d.id, d.image_path, d.defect_type, d.accuracy,
                       d.status, d.created_at, u.username
                FROM detections d
                LEFT JOIN users u ON u.id = d.technician_id
                WHERE 1=1{filter_sql}
                ORDER BY d.created_at DESC LIMIT 15""",
            filter_params,
        )
        data['recent_history'] = cursor.fetchall()

        # FIX: cek request.form.get('export') untuk trigger download CSV
        if request.method == 'POST' and request.form.get('export'):
            cursor.execute(
                f"""SELECT d.id, d.image_path, d.defect_type, d.accuracy,
                           d.status, d.created_at, u.username
                    FROM detections d
                    LEFT JOIN users u ON u.id = d.technician_id
                    WHERE 1=1{filter_sql}
                    ORDER BY d.created_at DESC""",
                filter_params,
            )
            export_rows = cursor.fetchall()

            out    = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(['ID', 'Technician', 'Defect Type', 'Accuracy', 'Status', 'Date', 'Image'])
            for row in export_rows:
                writer.writerow([
                    row.get('id'),
                    row.get('username') or 'Unknown',
                    row.get('defect_type'),
                    row.get('accuracy'),
                    row.get('status'),
                    row.get('created_at'),
                    row.get('image_path'),
                ])

            buf = io.BytesIO(out.getvalue().encode('utf-8'))
            buf.seek(0)
            return send_file(
                buf,
                as_attachment=True,
                download_name='detection_report.csv',
                mimetype='text/csv',
            )

    finally:
        cursor.close()
        conn.close()

    return render_template('admin/report.html', **data)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICIAN — DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/technician')
def technician_dashboard():
    if session.get('role') != 'technician':
        return redirect('/login')

    tech_id = session.get('user_id')
    conn    = get_db()
    cursor  = conn.cursor(dictionary=True)

    total_detections  = 0
    avg_accuracy      = 0
    top_defect        = 'N/A'
    defect_labels     = []
    defect_values     = []
    defect_summary    = []
    recent_detections = []

    try:
        cursor.execute(
            'SELECT COUNT(*) AS total, AVG(accuracy) AS avg_acc FROM detections WHERE technician_id = %s',
            (tech_id,),
        )
        row = cursor.fetchone()
        total_detections = row['total'] or 0
        avg_accuracy     = round(row['avg_acc'] or 0, 2)

        cursor.execute(
            """SELECT defect_type, COUNT(*) AS cnt FROM detections
               WHERE technician_id = %s
               GROUP BY defect_type ORDER BY cnt DESC""",
            (tech_id,),
        )
        defect_rows   = cursor.fetchall()
        counts        = {r['defect_type']: int(r['cnt']) for r in defect_rows}
        defect_labels = [r['defect_type'] for r in defect_rows]
        defect_values = [int(r['cnt'])    for r in defect_rows]
        if defect_rows:
            top_defect = defect_rows[0]['defect_type']

        defect_summary = _build_defect_summary(counts, total_detections)

        cursor.execute(
            """SELECT id, image_path, defect_type, accuracy, status, created_at
               FROM detections WHERE technician_id = %s
               ORDER BY created_at DESC LIMIT 6""",
            (tech_id,),
        )
        recent_detections = cursor.fetchall()
        for row in recent_detections:
            # FIX: get_image_url sekarang cek /static/ prefix, tidak salah folder lagi
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
        recent_detections=recent_detections,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICIAN — DETECTION PAGE
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/technician/detection')
def technician_detection():
    if session.get('role') != 'technician':
        return redirect('/login')
    return render_template('technician/detection.html')


# ─────────────────────────────────────────────────────────────────────────────
# DETECT (POST) — core pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _save_feature_map(filename: str) -> Optional[str]:
    """Generate and save the backbone feature-map heatmap.

    Returns the URL string, or None if no feature map is available.
    FIX: return type changed from 'str | None' to Optional[str]
         so this works on Python 3.8 and 3.9 as well as 3.10+.
    """
    if not _feature_maps:
        return None

    fmap = _feature_maps[0][0][0].numpy()     # shape: (H, W)
    fmap = (fmap - fmap.min()) / (fmap.max() - fmap.min() + 1e-8)

    feature_filename = f'feature_{filename}'
    feature_path     = os.path.join(RESULT_FOLDER, feature_filename)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.imshow(fmap, cmap='viridis')
    ax.axis('off')
    fig.savefig(feature_path, bbox_inches='tight', pad_inches=0)
    plt.close(fig)

    return f'/static/results/{feature_filename}'


@app.route('/detect', methods=['POST'])
def detect():
    if session.get('role') != 'technician':
        return redirect('/login')

    # ── validate upload ──────────────────────────────────────────────────────
    file = request.files.get('image')
    if not file or file.filename == '':
        return render_template('technician/detection.html',
                               error='Please select an image file first.')
    if not allowed_file(file.filename):
        return render_template('technician/detection.html',
                               error='Unsupported file type. Use PNG, JPG, or JPEG.')

    # ── save original upload ─────────────────────────────────────────────────
    filename = unique_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    original_image = f'/static/uploads/{filename}'

    # ── read image ───────────────────────────────────────────────────────────
    img = cv2.imread(filepath)
    if img is None:
        return render_template('technician/detection.html',
                               error='Could not read the uploaded image.')
    height, width = img.shape[:2]

    # ── step 1: resize 640×640 ───────────────────────────────────────────────
    resized         = cv2.resize(img, (640, 640))
    resize_filename = f'resize_{filename}'
    cv2.imwrite(os.path.join(RESULT_FOLDER, resize_filename), resized)
    resize_image = f'/static/results/{resize_filename}'

    # ── step 2: normalize (0–255 → 0–1, display only) ───────────────────────
    normalized_display = (resized.astype('float32') / 255.0 * 255).astype('uint8')
    norm_filename      = f'normalize_{filename}'
    cv2.imwrite(os.path.join(NORMALIZE_FOLDER, norm_filename), normalized_display)
    normalize_image = f'/static/normalize/{norm_filename}'

    # ── step 3: YOLO inference ───────────────────────────────────────────────
    try:
        results = model.predict(source=filepath, conf=0.25, save=False)
    except Exception as exc:
        print(f'[detect] model error: {exc}')
        return render_template('technician/detection.html',
                               error='Detection failed. Please try again.')

    # ── step 4: feature map ──────────────────────────────────────────────────
    feature_image = _save_feature_map(filename)

    # ── step 5: parse detections ─────────────────────────────────────────────
    result_obj     = results[0]
    defect_type    = 'No Defect'
    accuracy       = 0.0
    status         = 'NORMAL'
    detections     = []
    cropped_images = []

    if len(result_obj.boxes) > 0:
        confidences = [float(b.conf[0]) for b in result_obj.boxes]
        best_box    = result_obj.boxes[confidences.index(max(confidences))]

        defect_type = model.names[int(best_box.cls[0])]
        accuracy    = round(float(best_box.conf[0]) * 100, 2)
        status      = 'DEFECT'

        for i, box in enumerate(result_obj.boxes):
            cls_id        = int(box.cls[0])
            conf          = round(float(box.conf[0]) * 100, 2)
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append({
                'class': model.names[cls_id], 'confidence': conf,
                'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
            })

            cx1, cy1 = max(0, x1), max(0, y1)
            cx2, cy2 = min(width, x2), min(height, y2)
            if cx2 > cx1 and cy2 > cy1:
                crop          = img[cy1:cy2, cx1:cx2]
                crop_filename = f'crop_{i}_{filename}'
                cv2.imwrite(os.path.join(RESULT_FOLDER, crop_filename), crop)
                cropped_images.append({
                    'class':      model.names[cls_id],
                    'confidence': conf,
                    'image':      f'/static/results/{crop_filename}',
                })

    # ── step 6: save annotated result image ──────────────────────────────────
    result_filename = f'result_{filename}'
    cv2.imwrite(os.path.join(RESULT_FOLDER, result_filename), result_obj.plot())
    result_image = f'/static/results/{result_filename}'

    # ── step 7: persist to DB ────────────────────────────────────────────────
    conn   = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO detections
               (technician_id, image_path, defect_type, accuracy, status)
               VALUES (%s, %s, %s, %s, %s)""",
            (session.get('user_id'), result_image, defect_type, accuracy, status),
        )
        conn.commit()
    except Exception as exc:
        print(f'[detect] db insert error: {exc}')
    finally:
        cursor.close()
        conn.close()

    speed = result_obj.speed
    return render_template(
        'technician/detection.html',
        original_image=original_image,
        resize_image=resize_image,
        normalize_image=normalize_image,
        feature_image=feature_image,
        image=result_image,
        result=defect_type,
        accuracy=accuracy,
        status=status,
        width=width,
        height=height,
        preprocess_time=round(speed['preprocess'],  2),
        inference_time=round(speed['inference'],    2),
        postprocess_time=round(speed['postprocess'], 2),
        object_count=len(result_obj.boxes),
        detections=detections,
        cropped_images=cropped_images,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICIAN — HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/technician/history')
def technician_history():
    if session.get('role') != 'technician':
        return redirect('/login')

    tech_id = session.get('user_id')
    conn    = get_db()
    cursor  = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT id, image_path, defect_type, accuracy, status, created_at
               FROM detections WHERE technician_id = %s
               ORDER BY created_at DESC""",
            (tech_id,),
        )
        history_rows = cursor.fetchall()
        for row in history_rows:
            # FIX: get_image_url sekarang mengembalikan path /static/results/...
            # yang sudah disimpan di DB — gambar bounding-box yang muncul, bukan original
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

    tech_id = session.get('user_id')
    conn    = get_db()
    cursor  = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT id, image_path, defect_type, accuracy, status, created_at
               FROM detections WHERE id = %s AND technician_id = %s""",
            (detection_id, tech_id),
        )
        detection = cursor.fetchone()
        if not detection:
            return redirect(url_for('technician_history'))
        detection['image_url'] = get_image_url(detection['image_path'])
        detection['file_name'] = (
            os.path.basename(detection['image_path']) if detection['image_path'] else ''
        )
    finally:
        cursor.close()
        conn.close()

    return render_template('technician/detail.html', detection=detection)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICIAN — REPORT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/technician/report', methods=['GET', 'POST'])
def technician_report():
    if session.get('role') != 'technician':
        return redirect('/login')

    tech_id    = session.get('user_id')
    start_date = ''
    end_date   = ''
    error      = None
    report_rows   = []
    # FIX: default dict harus pakai .get() saat diakses — 'No Defect' tidak ada di DEFECT_TYPES
    defect_counts = {d: 0 for d in DEFECT_TYPES}

    if request.method == 'POST':
        start_date = request.form.get('start_date', '').strip()
        end_date   = request.form.get('end_date',   '').strip()
        if not start_date and not end_date:
            error = 'Please select a start date or end date.'

    # Build query
    base_sql = """
        SELECT id, image_path, defect_type, accuracy, status, created_at
        FROM detections WHERE technician_id = %s
    """
    params: list = [tech_id]

    if start_date and end_date:
        base_sql += ' AND DATE(created_at) BETWEEN %s AND %s'
        params.extend([start_date, end_date])
    elif start_date:
        base_sql += ' AND DATE(created_at) >= %s'
        params.append(start_date)
    elif end_date:
        base_sql += ' AND DATE(created_at) <= %s'
        params.append(end_date)

    base_sql += ' ORDER BY created_at DESC'

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(base_sql, params)
        report_rows = cursor.fetchall()

        for row in report_rows:
            # FIX: defect_type bisa 'No Defect' → pakai .get() agar tidak KeyError
            dt = row.get('defect_type') or 'No Defect'
            defect_counts[dt] = defect_counts.get(dt, 0) + 1
            row['image_url']  = get_image_url(row['image_path'])
            row['file_name']  = os.path.basename(row['image_path']) if row['image_path'] else ''

        total_count = len(report_rows)

        # FIX: export hanya jika tidak ada error validasi
        if request.method == 'POST' and request.form.get('export') and not error:
            wb = Workbook()
            ws = wb.active
            ws.title = 'Report'
            ws.append(['ID', 'Defect Type', 'Accuracy', 'Status', 'Date', 'File Name'])
            for row in report_rows:
                ws.append([
                    row['id'],
                    row.get('defect_type') or 'No Defect',
                    row['accuracy'],
                    row['status'],
                    row['created_at'],
                    os.path.basename(row['image_path']) if row['image_path'] else '',
                ])
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            return send_file(
                buf,
                as_attachment=True,
                download_name='technician_report.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )

    finally:
        cursor.close()
        conn.close()

    total_count    = len(report_rows)
    defect_summary = _build_defect_summary(defect_counts, total_count)

    return render_template(
        'technician/report.html',
        start_date=start_date,
        end_date=end_date,
        error=error,
        report_rows=report_rows,
        report_total=total_count,
        defect_summary=defect_summary,
        defect_labels=[d for d in DEFECT_TYPES if defect_counts.get(d, 0) > 0],
        defect_values=[defect_counts.get(d, 0) for d in DEFECT_TYPES if defect_counts.get(d, 0) > 0],
    )


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICIAN — SETTINGS & CHANGE PASSWORD
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/technician/settings')
def technician_settings():
    if session.get('role') != 'technician':
        return redirect('/login')
    return render_template('technician/settings.html')


@app.route('/change-password', methods=['POST'])
def change_password():
    if session.get('role') != 'technician':
        return redirect('/login')

    old_password = request.form['old_password']
    new_password = request.form['new_password']
    db_user      = get_user(session['username'])

    if db_user['password'] != hash_password(old_password):
        return render_template('technician/settings.html',
                               error='Old password is incorrect.')

    update_password(session['username'], new_password)
    return redirect('/technician')


# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True)