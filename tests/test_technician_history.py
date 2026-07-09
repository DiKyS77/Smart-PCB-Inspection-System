from unittest.mock import MagicMock
from datetime import datetime

def test_history(technician_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = [
        {
            "id": 1,
            "image_path": "/static/results/test.jpg",
            "defect_type": "short",
            "accuracy": 98,
            "status": "DEFECT",
            "created_at": datetime(2026, 1, 1, 10, 30)
        }
    ]

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = technician_client.get("/technician/history")

    assert response.status_code == 200

def test_history_detail(technician_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchone.return_value = {
        "id": 1,
        "image_path": "/static/results/test.jpg",
        "defect_type": "short",
        "accuracy": 98,
        "status": "DEFECT",
        "created_at": datetime(2026, 1, 1, 10, 30)
    }

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = technician_client.get("/technician/history/1")

    assert response.status_code == 200