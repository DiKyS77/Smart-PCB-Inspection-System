"""Exercise workflow against MySQL using temporary rows and a final rollback."""
import csv
import io
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as application
from db import get_db
from detection_store import save_detection


class TransactionConnection:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

    def commit(self):
        pass  # The harness keeps all fixture changes in one rollback-only transaction.

    def rollback(self):
        pass

    def close(self):
        pass


def run():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    counts_before = {}
    tables = ('users', 'detections', 'detection_history', 'detection_objects', 'inspection_images',
              'pcb_types', 'pcb_work_units', 'pcb_inspection_reviews', 'pcb_work_events')
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) AS n FROM {table}')
        counts_before[table] = cursor.fetchone()['n']
    conn.rollback()
    conn.start_transaction()
    proxy = TransactionConnection(conn)
    original_get_db = application.get_db
    application.get_db = lambda: proxy
    application.app.config['TESTING'] = True
    suffix = uuid.uuid4().hex[:10]
    ids = (-1900000001, -1900000002, -1900000003)
    checks = []

    def client(user_id, role):
        result = application.app.test_client()
        with result.session_transaction() as session:
            session.update(user_id=user_id, username=f'workflow-test-{suffix}-{role}', role=role, language='en',
                           workflow_csrf='integration-test-token')
        return result

    def post(client, path, data):
        return client.post(path, data={**data, 'csrf_token': 'integration-test-token'})

    def inspect(pcb, status='DEFECT'):
        return save_detection(proxy, technician_id=ids[1], pcb_id=pcb,
                              source_image='/static/uploads/workflow_test.png',
                              result_image='/static/results/workflow_test.png',
                              defect_type='short' if status == 'DEFECT' else 'No Defect',
                              status=status, objects=[], width=640, height=640, model_path='best.pt')

    try:
        for identifier, role in zip(ids, ('admin', 'technician', 'technician')):
            cursor.execute('INSERT INTO users (id,username,password,role,active) VALUES (%s,%s,%s,%s,1)',
                           (identifier, f'wf_{suffix}_{identifier}', 'test-only-no-login', role))
        admin, tech, other = client(ids[0], 'admin'), client(ids[1], 'technician'), client(ids[2], 'technician')
        pcb = f'WF-{suffix}'
        detection_id = inspect(pcb)
        cursor.execute('SELECT id FROM pcb_work_units WHERE technician_id=%s AND pcb_id=%s', (ids[1], pcb))
        unit_id = cursor.fetchone()['id']
        path = f'/inspection-workflow/unit/{unit_id}'
        assert admin.get('/inspection-workflow').status_code == 200
        assert tech.get(path).status_code == 200
        assert other.get(path).status_code == 403
        checks.append('Admin overview, technician detail and cross-user isolation')
        for kind, name in [('type', 'TYPE-' + suffix)]:
            assert post(admin, '/inspection-workflow/catalog', dict(kind=kind, name=name, description='Temporary test')).status_code == 302
        cursor.execute('SELECT id FROM pcb_types WHERE name=%s', ('TYPE-' + suffix,))
        type_id = cursor.fetchone()['id']
        assert post(admin, path, dict(status='Dikerjakan', notes='Mulai inspeksi', priority='Tinggi',
                                      pcb_type_id=type_id)).status_code == 302
        assert post(tech, path, dict(status='Selesai', notes='')).status_code == 302
        cursor.execute('SELECT work_status FROM pcb_work_units WHERE id=%s', (unit_id,))
        assert cursor.fetchone()['work_status'] == 'Dikerjakan'
        checks.append('PCB type assignment and completion blocked before verification')
        review_path = f'/inspection-workflow/review/{detection_id}'
        assert post(other, review_path, dict(verification='Dikonfirmasi')).status_code == 404
        assert post(admin, review_path, dict(verification='Dikonfirmasi')).status_code == 403
        assert post(tech, review_path, dict(verification='Dikoreksi', corrected_defect='spur', reason='Bentuk spur, bukan short')).status_code == 302
        cursor.execute('SELECT defect_type FROM detections WHERE id=%s', (detection_id,))
        assert cursor.fetchone()['defect_type'] == 'short'
        assert b'<strong>Spur</strong>' in admin.get(path).data
        checks.append('Technician correction visible to admin; AI original remains intact')
        query = f'/inspection-workflow?q={pcb}&pcb_type={type_id}&verification=Dikoreksi'
        result = admin.get(query)
        assert result.status_code == 200 and pcb.encode() in result.data
        export = admin.get(query + '&export=csv')
        assert export.status_code == 200
        exported_rows = list(csv.DictReader(io.StringIO(export.data.decode('utf-8-sig'))))
        assert any(row['PCB ID'] == pcb and row['Technician correction'] == 'Spur' for row in exported_rows)
        assert post(tech, path, dict(status='Selesai', notes='Pemeriksaan selesai')).status_code == 302
        new_id = inspect(pcb, 'NORMAL')
        cursor.execute('SELECT COUNT(*) AS n, MAX(work_status) AS work_status FROM pcb_work_units WHERE technician_id=%s AND pcb_id=%s', (ids[1], pcb))
        row = cursor.fetchone()
        assert row['n'] == 1 and row['work_status'] == 'Dikerjakan'
        assert str(new_id).encode() in admin.get(path).data
        assert post(tech, path, dict(status='Selesai', notes='')).status_code == 302
        cursor.execute('SELECT work_status FROM pcb_work_units WHERE id=%s', (unit_id,))
        assert cursor.fetchone()['work_status'] == 'Dikerjakan'
        checks.append('Filtered CSV, repeat inspection remains one unit and reopens work; latest review required')
        cursor.execute('SELECT COUNT(*) AS n FROM pcb_work_events WHERE unit_id=%s', (unit_id,))
        assert cursor.fetchone()['n'] >= 4
        assert admin.post('/inspection-workflow/catalog', data={'kind': 'type', 'name': 'bad'}).status_code == 400
        checks.append('Audit events and CSRF protection')
    finally:
        application.get_db = original_get_db
        conn.rollback()
        counts_after = {}
        for table in tables:
            cursor.execute(f'SELECT COUNT(*) AS n FROM {table}')
            counts_after[table] = cursor.fetchone()['n']
        cursor.close()
        conn.close()
    assert counts_before == counts_after, (counts_before, counts_after)
    result = dict(success=True, checks=checks, temporary_data_rolled_back=True,
                  counts_before=counts_before, counts_after=counts_after)
    output = ROOT / 'reports' / 'pcb_workflow_check.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
