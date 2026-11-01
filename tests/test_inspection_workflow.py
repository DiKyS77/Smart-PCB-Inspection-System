from datetime import datetime
from unittest.mock import MagicMock

import pytest
import app as application
from inspection_workflow import track_detection, unit_key


def csrf(client):
    with client.session_transaction() as session:
        session['workflow_csrf'] = 'test-workflow-token'
    return {'csrf_token': 'test-workflow-token'}


@pytest.fixture
def fake_db(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value = cursor
    monkeypatch.setattr(application, 'get_db', lambda: connection)
    return connection, cursor


def unit(technician=2):
    return dict(id=7, technician_id=technician, unit_key='pcb:PCB-001', pcb_id='PCB-001',
                pcb_type_id=None, work_status='Menunggu', priority='Sedang', notes='')


def test_anonymous_cannot_view_workflow():
    with application.app.test_client() as client:
        assert client.get('/inspection-workflow').status_code == 302


def test_technician_overview_uses_existing_history(technician_client, fake_db):
    response = technician_client.get('/inspection-workflow')
    assert response.status_code == 302
    assert response.location.endswith('/technician/history')


def test_filter_and_csv_use_same_query(admin_client, fake_db):
    _, cursor = fake_db
    cursor.fetchall.side_effect = [[], []]
    response = admin_client.get('/inspection-workflow?pcb_type=8&status=Dikerjakan&verification=Dikoreksi&export=csv')
    assert response.status_code == 200
    assert 'text/csv' in response.content_type
    assert cursor.execute.call_args_list[0].args[1] == ('8', 'Dikerjakan', 'Dikoreksi')


def test_unit_detail_and_audit_render(admin_client, fake_db):
    _, cursor = fake_db
    cursor.fetchone.return_value = unit()
    cursor.fetchall.side_effect = [[dict(id=1, created_at=datetime(2026, 10, 31),
                                        status='DEFECT', defect_type='short', source_image_path='',
                                        image_path='', verification='Dikoreksi', corrected_defect='spur',
                                        reviewer_name='Teknisi', reviewed_at=None, reason='Dilihat ulang')], [],
                                  [dict(event_type='Verifikasi teknisi', actor_name='Teknisi',
                                        created_at='2026-10-31', detection_id=1,
                                        before_json='{}', after_json='{"verification":"Dikoreksi"}')]]
    response = admin_client.get('/inspection-workflow/unit/7')
    assert response.status_code == 200
    assert b'Dikoreksi' in response.data
    assert b'Jejak perubahan' in response.data


def test_other_technician_cannot_access_unit(technician_client, fake_db):
    _, cursor = fake_db
    cursor.fetchone.return_value = unit(technician=99)
    assert technician_client.get('/inspection-workflow/unit/7').status_code == 403


def test_csrf_required(admin_client, fake_db):
    connection, _ = fake_db
    assert admin_client.post('/inspection-workflow/catalog', data={'kind': 'type', 'name': 'A'}).status_code == 400
    connection.commit.assert_not_called()


def test_technician_cannot_create_catalog(technician_client):
    assert technician_client.post('/inspection-workflow/catalog', data={**csrf(technician_client), 'kind': 'type', 'name': 'A'}).status_code == 403


def test_correction_requires_reason(technician_client, fake_db):
    connection, _ = fake_db
    response = technician_client.post('/inspection-workflow/review/1', data={
        **csrf(technician_client), 'verification': 'Dikoreksi', 'corrected_defect': 'short', 'reason': ''})
    assert response.status_code == 400
    connection.commit.assert_not_called()


def test_review_is_owned_and_does_not_overwrite_ai(technician_client, fake_db):
    connection, cursor = fake_db
    cursor.fetchone.side_effect = [dict(id=1, pcb_id='PCB-001', defect_type='short'),
                                   {'id': 7}, unit(), None]
    response = technician_client.post('/inspection-workflow/review/1', data={
        **csrf(technician_client), 'verification': 'Dikoreksi', 'corrected_defect': 'spur', 'reason': 'Bentuk spur pada gambar asli'})
    assert response.status_code == 302
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert 'technician_id=%s' in queries[0]
    assert not any('UPDATE detections' in sql for sql in queries)
    assert any('INSERT INTO pcb_work_events' in sql for sql in queries)
    connection.commit.assert_called_once()


def test_cannot_finish_unverified_latest_inspection(technician_client, fake_db):
    connection, cursor = fake_db
    cursor.fetchone.side_effect = [unit(), {'id': 5, 'verification': None}]
    response = technician_client.post('/inspection-workflow/unit/7', data={
        **csrf(technician_client), 'status': 'Selesai', 'notes': 'Sudah diperiksa'})
    assert response.status_code == 302
    connection.commit.assert_not_called()


def test_status_change_is_audited_and_atomic(technician_client, fake_db):
    connection, cursor = fake_db
    cursor.fetchone.return_value = unit()
    response = technician_client.post('/inspection-workflow/unit/7', data={
        **csrf(technician_client), 'status': 'Perlu Inspeksi Ulang', 'notes': 'Foto buram'})
    assert response.status_code == 302
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert any('INSERT INTO pcb_work_events' in query for query in queries)
    connection.commit.assert_called_once()


def test_audit_failure_rolls_back_change(technician_client, fake_db):
    connection, cursor = fake_db
    cursor.fetchone.return_value = unit()

    def execute(sql, params):
        if 'INSERT INTO pcb_work_events' in sql:
            raise RuntimeError('audit insert failed')

    cursor.execute.side_effect = execute
    with pytest.raises(RuntimeError):
        technician_client.post('/inspection-workflow/unit/7', data={
            **csrf(technician_client), 'status': 'Dikerjakan', 'notes': 'Mulai pemeriksaan'})
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_new_inspection_reopens_finished_unit():
    cursor = MagicMock()
    cursor.fetchone.return_value = (7, 'Selesai')
    track_detection(cursor, 2, 'PCB-001', 100)
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("SET work_status='Dikerjakan'" in sql for sql in statements)
    assert any('INSERT INTO pcb_work_events' in sql for sql in statements)
    assert unit_key(None, 11) != unit_key(None, 12)


@pytest.mark.parametrize('query', ['pcb_type=bad', 'status=invalid', 'verification=invalid'])
def test_invalid_filters(admin_client, query):
    assert admin_client.get('/inspection-workflow?' + query).status_code == 400


def test_batch_catalog_no_longer_supported(admin_client, fake_db):
    connection, _ = fake_db
    response = admin_client.post('/inspection-workflow/catalog', data={
        **csrf(admin_client), 'kind': 'batch', 'name': 'OLD-BATCH'})
    assert response.status_code == 400
    connection.commit.assert_not_called()


def test_workflow_has_no_batch_controls(admin_client, fake_db):
    _, cursor = fake_db
    cursor.fetchall.side_effect = [[], []]
    response = admin_client.get('/inspection-workflow')
    assert response.status_code == 200
    assert b'Batch' not in response.data
    assert b'name="batch"' not in response.data
