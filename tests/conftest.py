import os
import sys

# Tambahkan root project ke sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from app import app


@pytest.fixture
def admin_client():
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "admin"
            sess["role"] = "admin"

        yield client


@pytest.fixture
def technician_client():
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["username"] = "technician"
            sess["role"] = "technician"

        yield client