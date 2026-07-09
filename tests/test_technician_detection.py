import io

def test_detection_page(technician_client):

    response = technician_client.get("/technician/detection")

    assert response.status_code == 200


def test_detect_without_image(technician_client):

    response = technician_client.post("/detect", data={})

    assert response.status_code == 200


def test_wrong_extension(technician_client):

    data = {
        "image": (io.BytesIO(b"abc"), "gambar.txt")
    }

    response = technician_client.post(
        "/detect",
        data=data,
        content_type="multipart/form-data"
    )

    assert response.status_code == 200