import hashlib
import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

import app as application
import detection_store
from image_store import image_url, make_image


def png():
    return cv2.imencode('.png', np.zeros((12, 16, 3), dtype=np.uint8))[1].tobytes()


def test_image_url_only_accepts_inspection_images():
    assert image_url('/static/uploads/a.png') == '/images/uploads/a.png'
    assert image_url('a.png') == '/images/uploads/a.png'
    for invalid in ('/images/uploads/../config.py', '/images/other/a.png', '/etc/a.jpg'):
        with pytest.raises(ValueError):
            image_url(invalid)


def test_image_endpoint_requires_login_and_preserves_bytes(technician_client, monkeypatch):
    content = png()
    cursor = MagicMock()
    cursor.fetchone.return_value = dict(content=content, mime_type='image/png',
                                        sha256=hashlib.sha256(content).hexdigest())
    conn = MagicMock()
    conn.cursor.return_value = cursor
    monkeypatch.setattr(application, 'get_db', lambda: conn)
    response = technician_client.get('/images/uploads/a.png')
    assert response.status_code == 200
    assert response.data == content and response.mimetype == 'image/png'
    assert 'private' in response.headers['Cache-Control']
    assert cursor.execute.call_args.args[1] == ('/images/uploads/a.png', False, 2, 2, 2)
    cursor.fetchone.return_value = None
    assert technician_client.get('/images/uploads/another-user.png').status_code == 404
    with application.app.test_client() as anonymous:
        assert anonymous.get('/images/uploads/a.png').status_code == 302


def test_detection_keeps_original_and_generated_images_in_memory(technician_client, monkeypatch):
    content = png()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, None]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    monkeypatch.setattr(application, 'get_db', lambda: conn)
    result = SimpleNamespace(boxes=[], speed=dict(preprocess=1, inference=2, postprocess=1),
                             plot=lambda **kwargs: np.zeros((12, 16, 3), dtype=np.uint8))
    predict = MagicMock(return_value=[result])
    monkeypatch.setattr(application.model, 'predict', predict)
    monkeypatch.setattr(application, '_feature_maps', [])
    persist = MagicMock()
    monkeypatch.setattr(application, 'save_detection', persist)
    monkeypatch.setattr(cv2, 'imwrite', MagicMock(side_effect=AssertionError('Unexpected disk image')))
    response = technician_client.post('/detect', data={
        'pcb_id': 'DB-IMAGE', 'image': (io.BytesIO(content), 'board.png')})
    assert response.status_code == 200
    images = persist.call_args.kwargs['images']
    assert len(images) == 4
    assert images[0]['content'] == content
    assert all(item['path'].startswith('/images/') for item in images)
    assert isinstance(predict.call_args.kwargs['source'], np.ndarray)


def test_image_inserts_roll_back_when_detection_fails(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    def fail_on_detection(sql, params):
        if 'INSERT INTO detections' in sql:
            raise RuntimeError('Simulated failure')
    cursor.execute.side_effect = fail_on_detection
    monkeypatch.setattr(detection_store, '_model_digest', lambda *args: 'a' * 64)
    with pytest.raises(RuntimeError):
        detection_store.save_detection(conn, technician_id=2, pcb_id='DB-IMAGE',
            source_image='/images/uploads/a.png', result_image='/images/results/a.png',
            defect_type='No Defect', status='NORMAL', objects=[], width=16, height=12,
            model_path='best.pt', images=[make_image('/images/uploads/a.png', png())])
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
