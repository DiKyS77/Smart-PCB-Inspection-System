import pytest
import re

from app import app
from i18n import translate


def test_language_persists_between_public_pages_and_logout():
    with app.test_client() as client:
        assert 'Pemeriksaan PCB' in client.get('/').get_data(as_text=True)
        assert '<label for="identifier" class="form-label">ID atau nama pengguna</label>' in client.get('/login').get_data(as_text=True)
        response = client.post('/language', data={'language': 'en', 'next': '/login'})
        assert response.status_code == 303 and response.location == '/login'
        assert 'Welcome back.' in client.get('/login').get_data(as_text=True)
        client.get('/logout')
        with client.session_transaction() as session:
            assert session['language'] == 'en'
            assert 'role' not in session


@pytest.mark.parametrize('destination', ['https://example.com', '//example.com', '/\\example.com', '/\nexample.com', 'http://['])
def test_language_redirect_remains_local(destination):
    with app.test_client() as client:
        response = client.post('/language', data={'language': 'en', 'next': destination})
        assert response.location == '/'
        assert client.post('/language', data={'language': 'xx'}).status_code == 400


def test_translations_preserve_types_and_escape_user_values():
    with app.test_request_context('/'):
        assert translate(12) == 12
        assert translate('Dashboard') == 'Dasbor'
        from flask import session
        session['language'] = 'en'
        assert translate('Selesai') == 'Completed'
        assert translate('Dikerjakan') == 'In progress'


def test_admin_navigation_is_identical_across_pages(admin_client, monkeypatch):
    from unittest.mock import MagicMock
    cursor = MagicMock()
    cursor.fetchone.return_value = {'total': 0, 'defect_type': None, 'cnt': 0}
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.cursor.return_value = cursor
    monkeypatch.setattr('app.get_db', lambda: connection)
    navigation = []
    for path in ('/admin', '/admin/manage-user', '/admin/report', '/inspection-workflow'):
        response = admin_client.get(path)
        assert response.status_code == 200
        document = response.get_data(as_text=True)
        assert document.count('class="language-switch"') == 1
        menu = re.search(r'<nav class="menu">(.*?)</nav>', document, re.S)[0]
        navigation.append(re.sub(r' class="active"| aria-current="page"', '', menu))
        assert menu.count('aria-current="page"') == 1
        assert 'Manajemen Inspeksi PCB' in menu
        # The obsolete label can occur only in a translation alias, not visible markup.
        assert 'Tindak Lanjut PCB' not in re.sub(r'<script.*?</script>', '', document, flags=re.S)
    assert all(menu == navigation[0] for menu in navigation)


@pytest.mark.parametrize('language,header', [('id', 'Teknisi'), ('en', 'Technician')])
def test_report_export_follows_language(admin_client, monkeypatch, language, header):
    from unittest.mock import MagicMock
    cursor = MagicMock()
    cursor.fetchone.return_value = {'total': 0, 'defect_type': None, 'cnt': 0}
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.cursor.return_value = cursor
    monkeypatch.setattr('app.get_db', lambda: connection)
    with admin_client.session_transaction() as session:
        session['language'] = language
    response = admin_client.post('/admin/report', data={
        'start_date': '2026-10-01', 'end_date': '2026-10-31', 'export': '1'})
    assert response.status_code == 200 and response.mimetype == 'text/csv'
    assert header in response.get_data(as_text=True).splitlines()[0]


def test_report_language_switch_preserves_date_filters(technician_client, monkeypatch):
    from unittest.mock import MagicMock
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.cursor.return_value = cursor
    monkeypatch.setattr('app.get_db', lambda: connection)
    response = technician_client.post('/technician/report', data={
        'start_date': '2026-10-01', 'end_date': '2026-10-31'})
    assert 'next" value="/technician/report?start_date=2026-10-01&amp;end_date=2026-10-31' in response.get_data(as_text=True)
    technician_client.get('/technician/report?start_date=2026-10-01&end_date=2026-10-31')
    assert cursor.execute.call_args.args[1] == [2, '2026-10-01', '2026-10-31']
