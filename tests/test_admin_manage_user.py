from unittest.mock import MagicMock

def test_manage_user_page(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = [
        {
            "id": 1,
            "username": "technician",
            "role": "technician",
            "active": 1
        }
    ]

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.get("/admin/manage-user")

    assert response.status_code == 200
    
def test_add_user(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = [
        {
            "id": 100,
            "username": "tester",
            "role": "technician",
            "active": 1
        }
    ]

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    fake_conn.commit = MagicMock()
    fake_conn.rollback = MagicMock()

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.post(
        "/admin/manage-user",
        data={
            "action": "add",
            "user_id": "100",
            "username": "tester",
            "password": "abc123",
            "confirm_password": "abc123"
        }
    )

    assert response.status_code == 200
    fake_conn.commit.assert_called_once()
    
def test_edit_user(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = []

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    fake_conn.commit = MagicMock()
    fake_conn.rollback = MagicMock()

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.post(
        "/admin/manage-user",
        data={
            "action": "edit",
            "user_id": "1",
            "username": "newtech",
            "password": "",
            "confirm_password": ""
        }
    )

    assert response.status_code == 200
    fake_conn.commit.assert_called_once()
    
def test_deactivate_user(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = []

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    fake_conn.commit = MagicMock()
    fake_conn.rollback = MagicMock()

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.post(
        "/admin/manage-user",
        data={
            "action": "deactivate",
            "user_id": "2"
        }
    )

    assert response.status_code == 200
    fake_conn.commit.assert_called_once()
    
def test_activate_user(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = []

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    fake_conn.commit = MagicMock()
    fake_conn.rollback = MagicMock()

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.post(
        "/admin/manage-user",
        data={
            "action": "activate",
            "user_id": "2"
        }
    )

    assert response.status_code == 200
    fake_conn.commit.assert_called_once()
    
def test_delete_user(admin_client, monkeypatch):

    fake_cursor = MagicMock()

    fake_cursor.fetchall.return_value = []

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    fake_conn.commit = MagicMock()
    fake_conn.rollback = MagicMock()

    monkeypatch.setattr("app.get_db", lambda: fake_conn)

    response = admin_client.post(
        "/admin/manage-user",
        data={
            "action": "delete",
            "user_id": "2"
        }
    )

    assert response.status_code == 200
    fake_conn.commit.assert_called_once()