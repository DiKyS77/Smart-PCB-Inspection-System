from unittest.mock import MagicMock

def test_report(technician_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = []

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = technician_client.get("/technician/report")

    assert response.status_code == 200


def test_report_without_date(technician_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = []

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = technician_client.post("/technician/report", data={})

    assert response.status_code == 200