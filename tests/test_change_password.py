def test_change_password_wrong_old(technician_client, monkeypatch):

    monkeypatch.setattr(
        "app.get_user",
        lambda username: {
            "username":"technician",
            "password":"123"
        }
    )

    response = technician_client.post(
        "/change-password",
        data={
            "old_password":"abc",
            "new_password":"123456"
        }
    )

    assert response.status_code == 200