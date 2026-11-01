"""
Smart PCB Inspection System — Flask Application
================================================
Roles  : admin, technician
Model  : YOLOv8 (best.pt)
DB     : MySQL (via db.get_db())
"""

import csv
import io
import os
import time

import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')          # non-interactive backend — wajib di server
import matplotlib.pyplot as plt
from flask import Flask, redirect, render_template, request, send_file, session, url_for
from openpyxl import Workbook
from ultralytics import YOLO
from werkzeug.utils import secure_filename

from db import get_db, get_user, hash_password, update_password
from detection_store import save_detection
from inspection_workflow import create_workflow, migrate_workflow
from image_store import create_image_routes, image_url, make_image, migrate_image_schema, read_image
from i18n import init_languages, translate as _


# ─────────────────────────────────────────────────────────────────────────────
# APP CONFIG
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
init_languages(app)
app.register_blueprint(create_workflow(lambda: get_db()))
app.register_blueprint(create_image_routes(lambda: get_db()))

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

DEFECT_TYPES = [
    'missing_resistor', 'missing_buzzer', 'mouse_bite',
    'spur', 'missing_hole', 'short', 'open_circuit',
    'spurious_copper',
]

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB


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
    """Resolve image links to the authenticated database image endpoint."""
    return image_url(image_path)


@app.before_request
def redirect_legacy_image():
    if request.path.startswith(('/static/uploads/', '/static/results/', '/static/normalize/')):
        try:
            return redirect(image_url(request.path), code=302)
        except ValueError:
            return '', 404


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
                pcb_id         VARCHAR(100),
                source_image_path VARCHAR(255),
                image_path     VARCHAR(255),
                defect_type    VARCHAR(100),
                status         VARCHAR(50),
                follow_up_status VARCHAR(40) NOT NULL DEFAULT 'Belum ditinjau',
                created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'detections'
              AND COLUMN_NAME  = 'pcb_id'
        """)
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                'ALTER TABLE detections ADD COLUMN pcb_id VARCHAR(100) NULL AFTER technician_id'
            )

        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'detections'
              AND COLUMN_NAME  = 'source_image_path'
        """)
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """ALTER TABLE detections
                   ADD COLUMN source_image_path VARCHAR(255) NULL AFTER pcb_id"""
            )

        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'detections'
              AND COLUMN_NAME  = 'follow_up_status'
        """)
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """ALTER TABLE detections
                   ADD COLUMN follow_up_status VARCHAR(40) NOT NULL
                   DEFAULT 'Belum ditinjau' AFTER status"""
            )
        migrate_workflow(cursor)
        migrate_image_schema(cursor)
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
        error='Ukuran file maksimal 10 MB.'
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
    language = session.get('language', 'id')
    session.clear()
    session['language'] = language
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
            SELECT d.id, d.image_path, d.defect_type,
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
            f"""SELECT d.id, d.image_path, d.defect_type,
                       d.status, d.created_at, u.username
                FROM detections d
                LEFT JOIN users u ON u.id = d.technician_id
                WHERE 1=1{filter_sql}
                ORDER BY d.created_at DESC LIMIT 15""",
            filter_params,
        )
        data['recent_history'] = cursor.fetchall()

        if request.method == 'POST' and request.form.get('export'):
            cursor.execute(
                f"""SELECT d.id, d.image_path, d.defect_type,
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
            writer.writerow([_(label) for label in ('ID', 'Technician', 'Defect Type', 'Status', 'Date', 'Image')])
            for row in export_rows:
                writer.writerow([
                    row.get('id'),
                    row.get('username') or _('Unknown'),
                    _(row.get('defect_type')),
                    _(row.get('status')),
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
    top_defect        = 'N/A'
    defect_labels     = []
    defect_values     = []
    defect_summary    = []
    recent_detections = []

    try:
        cursor.execute(
            'SELECT COUNT(*) AS total FROM detections WHERE technician_id = %s',
            (tech_id,),
        )
        row = cursor.fetchone()
        total_detections = row['total'] or 0

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
            """SELECT id, image_path, defect_type, status, created_at
               FROM detections WHERE technician_id = %s
               ORDER BY created_at DESC LIMIT 6""",
            (tech_id,),
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

    conn   = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT DISTINCT pcb_id FROM detections
               WHERE technician_id = %s AND pcb_id IS NOT NULL AND pcb_id <> ''
               ORDER BY pcb_id""",
            (session.get('user_id'),),
        )
        existing_pcb_ids = [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'technician/detection.html',
        existing_pcb_ids=existing_pcb_ids,
        pcb_id=request.args.get('pcb_id', '')[:100],
    )


# ─────────────────────────────────────────────────────────────────────────────
# DETECT (POST) — core pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _save_feature_map(filename: str, images: list) -> str | None:
    """Encode the backbone feature map as an in-memory PNG asset."""
    if not _feature_maps:
        return None

    fmap = _feature_maps[0][0][0].numpy()     # shape: (H, W)
    fmap = (fmap - fmap.min()) / (fmap.max() - fmap.min() + 1e-8)

    feature_filename = f'feature_{os.path.splitext(filename)[0]}.png'
    feature_path = f'/images/results/{feature_filename}'

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.imshow(fmap, cmap='viridis')
    ax.axis('off')
    try:
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', pad_inches=0)
        images.append(make_image(feature_path, buffer.getvalue()))
    finally:
        plt.close(fig)
    return feature_path


def _encoded_image(path, pixels):
    success, content = cv2.imencode(os.path.splitext(path)[1], pixels)
    if not success:
        raise ValueError('Gambar gagal dikodekan')
    return make_image(path, content.tobytes())


@app.route('/detect', methods=['POST'])
def detect():
    if session.get('role') != 'technician':
        return redirect('/login')

    pcb_id = request.form.get('pcb_id', '').strip().upper()
    if not pcb_id:
        return render_template(
            'technician/detection.html',
            error='Please enter a PCB ID.',
            pcb_id=pcb_id,
        )
    if len(pcb_id) > 100:
        return render_template(
            'technician/detection.html',
            error='PCB ID must be 100 characters or fewer.',
            pcb_id=pcb_id,
        )

    # ── keep each PCB ID tied to its first registered original image ─────────
    file = request.files.get('image')
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT source_image_path FROM detections
               WHERE technician_id = %s AND pcb_id = %s
                 AND source_image_path IS NOT NULL
               ORDER BY id ASC LIMIT 1""",
            (session.get('user_id'), pcb_id),
        )
        registered_image = cursor.fetchone()
        if not registered_image:
            cursor.execute(
                """SELECT id FROM detections
                   WHERE technician_id = %s AND pcb_id = %s LIMIT 1""",
                (session.get('user_id'), pcb_id),
            )
            existing_pcb = cursor.fetchone()
        else:
            existing_pcb = None
    finally:
        cursor.close()
        conn.close()

    images = []
    if registered_image:
        if file and file.filename:
            return render_template(
                'technician/detection.html',
                error='PCB ID ini sudah terdaftar. Hapus file yang dipilih agar deteksi memakai gambar awal yang tersimpan untuk ID ini.',
                pcb_id=pcb_id,
            )

        source_image_path = image_url(registered_image[0])
        source_filename = os.path.basename(source_image_path.replace('\\', '/'))
        filename = unique_filename(source_filename)
        conn = get_db()
        try:
            stored_image = read_image(conn, source_image_path, session.get('user_id'))
        finally:
            conn.close()
        if not stored_image:
            return render_template(
                'technician/detection.html',
                error='Gambar asli PCB tidak ditemukan. Unggah gambar kembali.',
                pcb_id=pcb_id,
            )
        original_content = bytes(stored_image['content'])
    elif existing_pcb:
        return render_template(
            'technician/detection.html',
            error='PCB ID ini sudah digunakan, tetapi gambar aslinya tidak tersedia. Gunakan ID PCB baru atau pulihkan gambar aslinya.',
            pcb_id=pcb_id,
        )
    elif file and file.filename:
        if not allowed_file(file.filename):
            return render_template('technician/detection.html',
                                   error='Unsupported file type. Use PNG, JPG, or JPEG.',
                                   pcb_id=pcb_id)

        filename = unique_filename(file.filename)
        original_content = file.read()
        source_image_path = f'/images/uploads/{filename}'
    else:
        return render_template(
            'technician/detection.html',
            error='Pilih gambar untuk mendaftarkan PCB ID baru.',
            pcb_id=pcb_id,
        )

    original_image = source_image_path

    # ── read image ───────────────────────────────────────────────────────────
    try:
        img = cv2.imdecode(np.frombuffer(original_content, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        img = None
    if img is None:
        return render_template('technician/detection.html',
                               error='Could not read the uploaded image.',
                               pcb_id=pcb_id)
    height, width = img.shape[:2]
    if not registered_image:
        try:
            images.append(make_image(source_image_path, original_content))
        except ValueError:
            return render_template('technician/detection.html',
                                   error='Format gambar harus PNG atau JPEG.', pcb_id=pcb_id), 400

    # ── step 1: resize 640×640 ───────────────────────────────────────────────
    resized         = cv2.resize(img, (640, 640))
    resize_filename = f'resize_{filename}'
    resize_image = f'/images/results/{resize_filename}'
    images.append(_encoded_image(resize_image, resized))

    # ── step 2: normalize (0–255 → 0–1, display only) ───────────────────────
    normalized_display = (resized.astype('float32') / 255.0 * 255).astype('uint8')
    norm_filename      = f'normalize_{filename}'
    normalize_image = f'/images/normalize/{norm_filename}'
    images.append(_encoded_image(normalize_image, normalized_display))

    # ── step 3: YOLO inference ───────────────────────────────────────────────
    try:
        results = model.predict(source=img, conf=0.25, save=False)
    except Exception as exc:
        print(f'[detect] model error: {exc}')
        return render_template('technician/detection.html',
                               error='Detection failed. Please try again.',
                               pcb_id=pcb_id)

    # ── step 4: feature map ──────────────────────────────────────────────────
    feature_image = _save_feature_map(filename, images)

    # ── step 5: parse detections ─────────────────────────────────────────────
    result_obj     = results[0]
    defect_type    = 'No Defect'
    status         = 'NORMAL'
    detections     = []
    cropped_images = []

    if len(result_obj.boxes) > 0:
        best_box = max(result_obj.boxes, key=lambda box: float(box.conf[0]))

        defect_type = model.names[int(best_box.cls[0])]
        status      = 'DEFECT'

        for i, box in enumerate(result_obj.boxes):
            cls_id        = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append({
                'class_id': cls_id,
                'class': model.names[cls_id],
                'x1': max(0, min(width, x1)), 'y1': max(0, min(height, y1)),
                'x2': max(0, min(width, x2)), 'y2': max(0, min(height, y2)),
            })

            cx1, cy1 = max(0, x1), max(0, y1)
            cx2, cy2 = min(width, x2), min(height, y2)
            if cx2 > cx1 and cy2 > cy1:
                crop          = img[cy1:cy2, cx1:cx2]
                crop_filename = f'crop_{i}_{filename}'
                crop_image = f'/images/results/{crop_filename}'
                images.append(_encoded_image(crop_image, crop))
                cropped_images.append({
                    'class':      model.names[cls_id],
                    'image':      crop_image,
                })

    # ── step 6: save annotated result image ──────────────────────────────────
    result_filename = f'result_{filename}'
    result_image = f'/images/results/{result_filename}'
    images.append(_encoded_image(result_image, result_obj.plot(conf=False)))

    # ── step 7: persist to DB ────────────────────────────────────────────────
    conn   = get_db()
    try:
        save_detection(
            conn, technician_id=session.get('user_id'), pcb_id=pcb_id,
            source_image=source_image_path, result_image=result_image,
            defect_type=defect_type, status=status,
            objects=detections, width=width, height=height,
            model_path='best.pt',
            images=images,
        )
    except Exception as exc:
        print(f'[detect] db insert error: {exc}')
        return render_template(
            'technician/detection.html',
            error='Detection completed, but the result could not be saved.',
            pcb_id=pcb_id,
        ), 500
    finally:
        conn.close()

    speed = result_obj.speed
    return render_template(
        'technician/detection.html',
        original_image=original_image,
        pcb_id=pcb_id,
        resize_image=resize_image,
        normalize_image=normalize_image,
        feature_image=feature_image,
        image=result_image,
        result=defect_type,
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
            """SELECT id, pcb_id, image_path, defect_type, status,
                      follow_up_status, created_at
               FROM detections WHERE technician_id = %s
               ORDER BY created_at DESC""",
            (tech_id,),
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

    return redirect(url_for('workflow.from_inspection', detection_id=detection_id))


@app.route('/technician/history/<int:detection_id>/follow-up', methods=['POST'])
def update_follow_up_status(detection_id):
    if session.get('role') != 'technician':
        return redirect('/login')
    # Old bookmarked forms lead to the audited unit workflow without changing data.
    return redirect(url_for('workflow.from_inspection', detection_id=detection_id))


# ─────────────────────────────────────────────────────────────────────────────
# TECHNICIAN — REPORT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/technician/report', methods=['GET', 'POST'])
def technician_report():
    if session.get('role') != 'technician':
        return redirect('/login')

    tech_id    = session.get('user_id')
    start_date = request.args.get('start_date', '').strip()
    end_date   = request.args.get('end_date', '').strip()
    error      = None
    report_rows   = []
    defect_counts = {d: 0 for d in DEFECT_TYPES}

    if request.method == 'POST':
        start_date = request.form.get('start_date', '').strip()
        end_date   = request.form.get('end_date',   '').strip()
        if not start_date and not end_date:
            error = 'Please select a start date or end date.'

    # Build query
    base_sql = """
        SELECT id, pcb_id, image_path, defect_type, status,
               follow_up_status, created_at
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
            dt = row.get('defect_type') or 'No Defect'
            defect_counts[dt] = defect_counts.get(dt, 0) + 1
            row['image_url']  = get_image_url(row['image_path'])
            row['file_name']  = os.path.basename(row['image_path']) if row['image_path'] else ''

        total_count = len(report_rows)

        if request.method == 'POST' and request.form.get('export') and not error:
            wb = Workbook()
            ws = wb.active
            ws.title = _('Report')
            ws.append([_(label) for label in (
                'Inspection ID', 'PCB ID', 'Defect Type',
                'Detection Status', 'Follow-up Status', 'Date', 'File Name',
            )])
            for row in report_rows:
                ws.append([
                    row['id'],
                    row.get('pcb_id') or '',
                    _(row.get('defect_type') or 'No Defect'),
                    _(row['status']),
                    _(row['follow_up_status']),
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
