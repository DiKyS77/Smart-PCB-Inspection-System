from unittest.mock import MagicMock
from datetime import datetime


def create_mock_connection():

    fake_cursor = MagicMock()

    # fetchone() dipanggil 4 kali
    fake_cursor.fetchone.side_effect = [
        {"total": 20},                 # total detections
        {"total": 5},                  # total technicians
        {"total": 4},                  # active technicians
        {"defect_type": "short"}       # top defect
    ]

    # fetchall() dipanggil 3 kali
    fake_cursor.fetchall.side_effect = [

        # Daily chart
        [
            {
                "day": datetime(2026, 1, 1).date(),
                "cnt": 10
            }
        ],

        # Defect chart
        [
            {
                "defect_type": "short",
                "cnt": 10
            }
        ],

        # Recent history
        [
            {
                "id": 1,
                "image_path": "/static/results/test.jpg",
                "defect_type": "short",

                "status": "DEFECT",
                "created_at": datetime(2026, 1, 1, 10, 30),
                "username": "technician"
            }
        ]
    ]

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    fake_conn.commit = MagicMock()
    fake_conn.rollback = MagicMock()

    return fake_conn


def test_admin_report_page(admin_client, monkeypatch):

    fake_conn = create_mock_connection()

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.get("/admin/report")

    assert response.status_code == 200


def test_admin_report_filter(admin_client, monkeypatch):

    fake_conn = create_mock_connection()

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.post(
        "/admin/report",
        data={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31"
        }
    )

    assert response.status_code == 200


def test_admin_report_export(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchone.side_effect = [
        {"total": 20},
        {"total": 5},
        {"total": 4},
        {"defect_type": "short"}
    ]

    fake_cursor.fetchall.side_effect = [

        # daily
        [
            {
                "day": datetime(2026, 1, 1).date(),
                "cnt": 10
            }
        ],

        # defect
        [
            {
                "defect_type": "short",
                "cnt": 10
            }
        ],

        # recent history
        [
            {
                "id": 1,
                "image_path": "/static/results/test.jpg",
                "defect_type": "short",

                "status": "DEFECT",
                "created_at": datetime(2026, 1, 1, 10, 30),
                "username": "technician"
            }
        ],

        # export csv
        [
            {
                "id": 1,
                "image_path": "/static/results/test.jpg",
                "defect_type": "short",

                "status": "DEFECT",
                "created_at": datetime(2026, 1, 1, 10, 30),
                "username": "technician"
            }
        ]
    ]

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.post(
        "/admin/report",
        data={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "export": "1"
        }
    )

    assert response.status_code == 200
    assert response.mimetype == "text/csv"