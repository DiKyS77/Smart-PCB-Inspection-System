from unittest.mock import MagicMock
from datetime import datetime

def test_admin_dashboard(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    # fetchone()
    fake_cursor.fetchone.side_effect = [
        {"total": 25},                           # total detections
        {"total": 5},                            # total technicians
        {"total": 4},                            # active technicians
        {"defect_type": "short"}                 # top defect
    ]

    # fetchall()
    fake_cursor.fetchall.side_effect = [

        # Daily chart
        [
            {"day": datetime(2026, 1, 1).date(), "cnt": 10},
            {"day": datetime(2026, 1, 2).date(), "cnt": 15},
        ],

        # Defect chart
        [
            {"defect_type": "short", "cnt": 10},
            {"defect_type": "open_circuit", "cnt": 5},
        ],

        # Top technician
        [
            {
                "username": "technician",
                "total_detections": 15
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

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.get("/admin")

    assert response.status_code == 200