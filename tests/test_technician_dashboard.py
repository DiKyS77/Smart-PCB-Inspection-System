from unittest.mock import MagicMock
from datetime import datetime

def test_dashboard(technician_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchone.side_effect = [
        {"total":5}
    ]

    fake_cursor.fetchall.side_effect = [
        [
            {"defect_type":"short","cnt":3},
            {"defect_type":"open_circuit","cnt":2}
        ],
        [
            {
                "id":1,
                "image_path":"/static/results/test.jpg",
                "defect_type":"short",

                "status":"DEFECT",
                "created_at": datetime(2026, 1, 1, 10, 30)
            }
        ]
    ]

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = technician_client.get("/technician")

    assert response.status_code == 200