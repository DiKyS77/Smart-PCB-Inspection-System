"""PCB ID tracking, unit follow-up, and technician reviews without replacing AI data."""
import csv
import io
import json
import os
import secrets
from image_store import image_url
from i18n import translate as _
from functools import wraps

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for

STATUSES = ('Menunggu', 'Dikerjakan', 'Perlu Inspeksi Ulang', 'Selesai')
PRIORITIES = ('Rendah', 'Sedang', 'Tinggi')
REVIEWS = ('Belum diverifikasi', 'Dikonfirmasi', 'Dikoreksi')
DEFECTS = ('missing_resistor', 'missing_buzzer', 'mouse_bite', 'spur',
           'missing_hole', 'short', 'open_circuit', 'spurious_copper', 'No Defect')


def migrate_workflow(cursor):
    """Additive, repeatable schema; existing inspection predictions stay intact."""
    statements = [
        '''CREATE TABLE IF NOT EXISTS pcb_types (
            id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE,
            description VARCHAR(500) NOT NULL DEFAULT '') ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS pcb_work_units (
            id INT AUTO_INCREMENT PRIMARY KEY, technician_id INT NOT NULL,
            unit_key VARCHAR(120) NOT NULL, pcb_id VARCHAR(100),
            pcb_type_id INT NULL,
            work_status VARCHAR(40) NOT NULL DEFAULT 'Menunggu',
            priority VARCHAR(20) NOT NULL DEFAULT 'Sedang',
            notes TEXT, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unit_identity (technician_id, unit_key),
            FOREIGN KEY (pcb_type_id) REFERENCES pcb_types(id)) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS pcb_inspection_reviews (
            detection_id INT PRIMARY KEY, verification VARCHAR(40) NOT NULL,
            corrected_defect VARCHAR(100) NULL, reason TEXT NOT NULL,
            reviewer_id INT NOT NULL, reviewer_name VARCHAR(255) NOT NULL,
            reviewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS pcb_work_events (
            id INT AUTO_INCREMENT PRIMARY KEY, unit_id INT NOT NULL,
            detection_id INT NULL, actor_id INT NOT NULL,
            actor_name VARCHAR(255) NOT NULL, event_type VARCHAR(40) NOT NULL,
            before_json TEXT NOT NULL, after_json TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY unit_events (unit_id, id)) ENGINE=InnoDB''',
    ]
    for statement in statements:
        cursor.execute(statement)
    cursor.execute('''INSERT IGNORE INTO pcb_work_units
        (technician_id, unit_key, pcb_id, work_status)
        SELECT d.technician_id,
               CASE WHEN COALESCE(d.pcb_id, '') = '' THEN CONCAT('@inspection:', d.id)
                    ELSE CONCAT('pcb:', d.pcb_id) END, d.pcb_id,
               CASE d.follow_up_status
                 WHEN 'Sedang diperiksa' THEN 'Dikerjakan'
                 WHEN 'Perlu perbaikan' THEN 'Perlu Inspeksi Ulang'
                 WHEN 'Dikerjakan' THEN 'Dikerjakan'
                 WHEN 'Perlu Inspeksi Ulang' THEN 'Perlu Inspeksi Ulang'
                 WHEN 'Selesai' THEN 'Selesai' ELSE 'Menunggu' END
        FROM detections d
        WHERE d.technician_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM detections newer
              WHERE newer.technician_id = d.technician_id
                AND COALESCE(d.pcb_id, '') <> '' AND newer.pcb_id = d.pcb_id
                AND (newer.created_at > d.created_at OR
                    (newer.created_at = d.created_at AND newer.id > d.id)))''')


def unit_key(pcb_id, detection_id):
    return f'pcb:{pcb_id}' if pcb_id else f'@inspection:{detection_id}'


def track_detection(cursor, technician_id, pcb_id, detection_id):
    """Called inside the inspection transaction, including reinspection reset."""
    key = unit_key(pcb_id, detection_id)
    cursor.execute('''INSERT INTO pcb_work_units (technician_id, unit_key, pcb_id)
                      VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)''',
                   (technician_id, key, pcb_id))
    cursor.execute('''SELECT id, work_status FROM pcb_work_units
                      WHERE technician_id=%s AND unit_key=%s FOR UPDATE''', (technician_id, key))
    unit_id, status = cursor.fetchone()
    if status in ('Selesai', 'Perlu Inspeksi Ulang'):
        cursor.execute("UPDATE pcb_work_units SET work_status='Dikerjakan', updated_at=NOW() WHERE id=%s", (unit_id,))
        cursor.execute('''INSERT INTO pcb_work_events
            (unit_id,detection_id,actor_id,actor_name,event_type,before_json,after_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (unit_id, detection_id, technician_id, 'Teknisi', 'Inspeksi ulang',
             json.dumps({'status': status}), json.dumps({'status': 'Dikerjakan', 'inspection': detection_id})))
        status = 'Dikerjakan'
    cursor.execute('''UPDATE detections SET follow_up_status=%s WHERE technician_id=%s AND
        CASE WHEN COALESCE(pcb_id,'')='' THEN CONCAT('@inspection:',id)
             ELSE CONCAT('pcb:',pcb_id) END=%s''', (status, technician_id, key))


def create_workflow(get_connection):
    bp = Blueprint('workflow', __name__)

    def authorized(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get('role') not in ('admin', 'technician') or not session.get('user_id'):
                return redirect('/login')
            if request.method == 'POST':
                token = session.get('workflow_csrf', '')
                if not token or not secrets.compare_digest(token, request.form.get('csrf_token', '')):
                    abort(400, _('Form kedaluwarsa. Muat ulang halaman lalu coba kembali.'))
            return view(*args, **kwargs)
        return wrapped

    @bp.context_processor
    def workflow_context():
        if 'workflow_csrf' not in session:
            session['workflow_csrf'] = secrets.token_hex(32)
        return dict(work_statuses=STATUSES, priorities=PRIORITIES, review_states=REVIEWS,
                    defect_options=DEFECTS, workflow_csrf=session['workflow_csrf'])

    def event(cursor, unit, kind, before, after, detection_id=None):
        cursor.execute('''INSERT INTO pcb_work_events
            (unit_id,detection_id,actor_id,actor_name,event_type,before_json,after_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (unit['id'], detection_id, session['user_id'], session.get('username', ''),
             kind, json.dumps(before, ensure_ascii=False, default=str),
             json.dumps(after, ensure_ascii=False, default=str)))

    def get_unit(cursor, unit_id, lock=False):
        cursor.execute('SELECT * FROM pcb_work_units WHERE id=%s' + (' FOR UPDATE' if lock else ''), (unit_id,))
        unit = cursor.fetchone()
        if not unit:
            abort(404)
        if session['role'] != 'admin' and unit['technician_id'] != session['user_id']:
            abort(403)
        return unit

    @bp.route('/inspection-workflow')
    @authorized
    def overview():
        if session['role'] == 'technician':
            return redirect(url_for('technician_history'))
        filters = {key: request.args.get(key, '').strip() for key in ('q', 'pcb_type', 'status', 'verification')}
        params, where = [], []
        if session['role'] != 'admin':
            where.append('w.technician_id=%s')
            params.append(session['user_id'])
        if len(filters['q']) > 100:
            abort(400)
        if filters['q']:
            where.append("(w.pcb_id LIKE %s OR t.name LIKE %s)")
            params.extend([f"%{filters['q']}%"] * 2)
        for key, column in (('pcb_type', 'w.pcb_type_id'),):
            if filters[key]:
                if not filters[key].isascii() or not filters[key].isdigit():
                    abort(400)
                where.append(column + '=%s')
                params.append(filters[key])
        for key, column, allowed in (('status', 'w.work_status', STATUSES),
                                     ('verification', "COALESCE(r.verification,'Belum diverifikasi')", REVIEWS)):
            if filters[key]:
                if filters[key] not in allowed:
                    abort(400)
                where.append(column + '=%s')
                params.append(filters[key])
        query = '''SELECT w.*, t.name AS type_name,
                   u.username AS technician_name, d.id AS detection_id,
                   d.defect_type, d.status AS ai_status, d.created_at AS inspected_at,
                   COALESCE(r.verification,'Belum diverifikasi') AS verification,
                   r.corrected_defect
                   FROM pcb_work_units w
                   LEFT JOIN pcb_types t ON t.id=w.pcb_type_id
                   LEFT JOIN users u ON u.id=w.technician_id
                   JOIN detections d ON d.id=(SELECT latest.id FROM detections latest
                     WHERE latest.technician_id=w.technician_id
                     AND CASE WHEN COALESCE(latest.pcb_id,'')='' THEN CONCAT('@inspection:',latest.id)
                              ELSE CONCAT('pcb:',latest.pcb_id) END=w.unit_key
                     ORDER BY latest.created_at DESC, latest.id DESC LIMIT 1)
                   LEFT JOIN pcb_inspection_reviews r ON r.detection_id=d.id'''
        if where:
            query += ' WHERE ' + ' AND '.join(where)
        query += ' ORDER BY w.updated_at DESC, w.id DESC'
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            cursor.execute('SELECT * FROM pcb_types ORDER BY name')
            types = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        counts = {status: sum(row['work_status'] == status for row in rows) for status in STATUSES}
        if request.args.get('export') == 'csv':
            stream = io.StringIO(newline='')
            writer = csv.writer(stream)
            writer.writerow([_(label) for label in ('PCB ID', 'PCB type', 'Technician', 'Work status', 'Priority', 'Main AI result', 'Latest verification', 'Technician correction')])
            for row in rows:
                fields = ('pcb_id', 'type_name', 'technician_name', 'work_status', 'priority', 'defect_type', 'verification', 'corrected_defect')
                values = [_(row.get(key) or '') if key in fields[3:] else (row.get(key) or '') for key in fields]
                writer.writerow([("'" + str(value)) if str(value).lstrip().startswith(('=', '+', '-', '@')) else value for value in values])
            return Response('\ufeff' + stream.getvalue(), mimetype='text/csv',
                            headers={'Content-Disposition': 'attachment; filename=pcb_inspection_management.csv'})
        return render_template('admin/follow_up.html', rows=rows,
                               types=types, filters=filters, counts=counts)

    @bp.route('/inspection-workflow/catalog', methods=['POST'])
    @authorized
    def catalog():
        if session['role'] != 'admin':
            abort(403)
        kind = request.form.get('kind')
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if kind != 'type' or not name or len(name) > 100 or len(description) > 500:
            abort(400, _('Nama wajib diisi, maksimal 100 karakter; deskripsi maksimal 500 karakter.'))
        conn = get_connection()
        cursor = conn.cursor()
        try:
            table, column = 'pcb_types', 'name'
            try:
                cursor.execute(f'INSERT INTO {table} ({column},description) VALUES (%s,%s)', (name, description))
                conn.commit()
                flash('Data berhasil ditambahkan.', 'success')
            except Exception as error:
                conn.rollback()
                if getattr(error, 'errno', None) == 1062:
                    flash('Nama jenis PCB sudah tersedia.', 'danger')
                else:
                    raise
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('workflow.overview'))

    @bp.route('/inspection-workflow/unit/<int:unit_id>', methods=['GET', 'POST'])
    @authorized
    def detail(unit_id):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            unit = get_unit(cursor, unit_id, lock=request.method == 'POST')
            if request.method == 'POST':
                status = request.form.get('status', '')
                notes = request.form.get('notes', '').strip()
                if status not in STATUSES or len(notes) > 2000:
                    abort(400, _('Status tidak valid atau catatan melebihi 2000 karakter.'))
                if status == 'Perlu Inspeksi Ulang' and not notes:
                    abort(400, _('Isi alasan inspeksi ulang.'))
                if status == 'Selesai':
                    cursor.execute('''SELECT d.id, r.verification FROM detections d
                        LEFT JOIN pcb_inspection_reviews r ON r.detection_id=d.id
                        WHERE d.technician_id=%s AND
                        CASE WHEN COALESCE(d.pcb_id,'')='' THEN CONCAT('@inspection:',d.id)
                             ELSE CONCAT('pcb:',d.pcb_id) END=%s
                        ORDER BY d.created_at DESC,d.id DESC LIMIT 1''', (unit['technician_id'], unit['unit_key']))
                    latest = cursor.fetchone()
                    if not latest or latest['verification'] not in ('Dikonfirmasi', 'Dikoreksi'):
                        flash('Verifikasi hasil inspeksi terbaru terlebih dahulu sebelum menyelesaikan unit.', 'danger')
                        return redirect(url_for('workflow.detail', unit_id=unit_id))
                updates = {'work_status': status, 'notes': notes}
                # Admin controls catalog assignment and priority. Technician owns technical review.
                if session['role'] == 'admin':
                    priority = request.form.get('priority', '')
                    if priority not in PRIORITIES:
                        abort(400)
                    updates['priority'] = priority
                    for field, table in (('pcb_type_id', 'pcb_types'),):
                        value = request.form.get(field, '')
                        if value:
                            if not value.isascii() or not value.isdigit():
                                abort(400)
                            cursor.execute(f'SELECT id FROM {table} WHERE id=%s', (value,))
                            if not cursor.fetchone():
                                abort(400, _('Jenis PCB tidak ditemukan.'))
                        updates[field] = int(value) if value else None
                before = {key: unit.get(key) for key in updates}
                if before != updates:
                    assignments = ','.join(f'{key}=%s' for key in updates)
                    cursor.execute(f'UPDATE pcb_work_units SET {assignments},updated_at=NOW() WHERE id=%s', (*updates.values(), unit_id))
                    cursor.execute('''UPDATE detections SET follow_up_status=%s
                        WHERE technician_id=%s AND
                        CASE WHEN COALESCE(pcb_id,'')='' THEN CONCAT('@inspection:',id)
                             ELSE CONCAT('pcb:',pcb_id) END=%s''', (status, unit['technician_id'], unit['unit_key']))
                    event(cursor, unit, 'Tindak lanjut', before, updates)
                conn.commit()
                flash('Tindak lanjut berhasil disimpan.', 'success')
                return redirect(url_for('workflow.detail', unit_id=unit_id))
            cursor.execute('''SELECT d.*, r.verification, r.corrected_defect, r.reason,
                      r.reviewer_name,r.reviewed_at
                FROM detections d LEFT JOIN pcb_inspection_reviews r ON r.detection_id=d.id
                WHERE d.technician_id=%s AND
                  CASE WHEN COALESCE(d.pcb_id,'')='' THEN CONCAT('@inspection:',d.id)
                       ELSE CONCAT('pcb:',d.pcb_id) END=%s
                ORDER BY d.created_at DESC,d.id DESC''', (unit['technician_id'], unit['unit_key']))
            inspections = cursor.fetchall()
            cursor.execute('SELECT * FROM pcb_types ORDER BY name')
            types = cursor.fetchall()
            cursor.execute('SELECT * FROM pcb_work_events WHERE unit_id=%s ORDER BY id DESC', (unit_id,))
            events = cursor.fetchall()
            labels = {'work_status': 'Status pengerjaan', 'status': 'Status pengerjaan',
                      'notes': 'Catatan', 'priority': 'Prioritas',
                      'pcb_type_id': 'Jenis PCB', 'verification': 'Verifikasi',
                      'corrected_defect': 'Hasil koreksi', 'reason': 'Alasan', 'inspection': 'Nomor inspeksi'}
            catalogs = {'pcb_type_id': {item['id']: item['name'] for item in types}}

            def display(key, value):
                if value is None or value == '':
                    return '—'
                return catalogs.get(key, {}).get(value, value)

            for item in events:
                before = json.loads(item['before_json'])
                after = json.loads(item['after_json'])
                item['changes'] = [dict(label=labels.get(key, key),
                                        before=display(key, before.get(key)), after=display(key, value))
                                   for key, value in after.items() if key != 'batch_id' and before.get(key) != value]
            detection = next((item for item in inspections
                              if str(item['id']) == request.args.get('inspection_id')), None)
            detection = detection or (inspections[0] if inspections else None)
            if session['role'] == 'technician' and not detection:
                abort(404)
            if detection:
                path = detection.get('image_path') or ''
                detection['image_url'] = image_url(path)
                detection['file_name'] = os.path.basename(path)
            for inspection in inspections:
                for column in ('source_image_path', 'image_path'):
                    inspection[column] = image_url(inspection.get(column))
            template = 'admin/follow_up_detail.html' if session['role'] == 'admin' else 'technician/detail.html'
            return render_template(template, unit=unit, inspections=inspections,
                                   types=types, events=events, detection=detection)
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @bp.route('/inspection-workflow/review/<int:detection_id>', methods=['POST'])
    @authorized
    def review(detection_id):
        if session['role'] != 'technician':
            abort(403)
        verification = request.form.get('verification', '')
        correction = request.form.get('corrected_defect', '').strip()
        reason = request.form.get('reason', '').strip()
        if verification not in ('Dikonfirmasi', 'Dikoreksi') or len(reason) > 2000:
            abort(400, _('Verifikasi tidak valid atau catatan terlalu panjang.'))
        if verification == 'Dikoreksi' and (correction not in DEFECTS or not reason):
            abort(400, _('Koreksi wajib memiliki jenis cacat dan alasan.'))
        if verification == 'Dikonfirmasi':
            correction = None
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT * FROM detections WHERE id=%s AND technician_id=%s', (detection_id, session['user_id']))
            detection = cursor.fetchone()
            if not detection:
                abort(404)
            cursor.execute('SELECT id FROM pcb_work_units WHERE technician_id=%s AND unit_key=%s',
                           (session['user_id'], unit_key(detection['pcb_id'], detection_id)))
            row = cursor.fetchone()
            if not row:
                abort(404)
            unit = get_unit(cursor, row['id'], lock=True)
            if verification == 'Dikoreksi' and correction == detection['defect_type']:
                abort(400, _('Koreksi harus berbeda dari hasil AI; gunakan Dikonfirmasi jika sesuai.'))
            cursor.execute('SELECT * FROM pcb_inspection_reviews WHERE detection_id=%s', (detection_id,))
            old = cursor.fetchone()
            after = dict(verification=verification, corrected_defect=correction, reason=reason)
            before = {key: old.get(key) for key in after} if old else {}
            cursor.execute('''INSERT INTO pcb_inspection_reviews
                (detection_id,verification,corrected_defect,reason,reviewer_id,reviewer_name)
                VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                verification=VALUES(verification),corrected_defect=VALUES(corrected_defect),
                reason=VALUES(reason),reviewer_id=VALUES(reviewer_id),
                reviewer_name=VALUES(reviewer_name),reviewed_at=NOW()''',
                (detection_id, verification, correction, reason, session['user_id'], session.get('username', '')))
            event(cursor, unit, 'Verifikasi teknisi', before, after, detection_id)
            cursor.execute('UPDATE pcb_work_units SET updated_at=NOW() WHERE id=%s', (unit['id'],))
            conn.commit()
            flash('Verifikasi tersimpan. Prediksi AI asli tetap dipertahankan.', 'success')
            return redirect(url_for('workflow.detail', unit_id=unit['id'], inspection_id=detection_id))
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @bp.route('/inspection-workflow/from-inspection/<int:detection_id>')
    @authorized
    def from_inspection(detection_id):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT id,pcb_id,technician_id FROM detections WHERE id=%s', (detection_id,))
            detection = cursor.fetchone()
            if not detection:
                abort(404)
            if session['role'] != 'admin' and detection['technician_id'] != session['user_id']:
                abort(403)
            cursor.execute('SELECT id FROM pcb_work_units WHERE technician_id=%s AND unit_key=%s',
                           (detection['technician_id'], unit_key(detection['pcb_id'], detection_id)))
            unit = cursor.fetchone()
            if not unit:
                abort(404)
            return redirect(url_for('workflow.detail', unit_id=unit['id'], inspection_id=detection_id))
        finally:
            cursor.close()
            conn.close()

    return bp
