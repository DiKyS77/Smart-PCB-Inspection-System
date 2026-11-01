"""Database image storage shared by detection, history and migration."""
import hashlib
import io
from pathlib import PurePosixPath

from flask import Blueprint, abort, redirect, send_file, session


IMAGE_FOLDERS = ('uploads', 'results', 'normalize')


def image_url(path):
    if not path:
        return ''
    path = path.replace('\\', '/')
    if '/' not in path:
        path = '/images/uploads/' + path
    elif path.startswith('/static/'):
        path = '/images/' + path[len('/static/'):]
    parts = path.split('/')
    if (len(parts) != 4 or parts[:2] != ['', 'images']
            or parts[2] not in IMAGE_FOLDERS or parts[3] in ('', '.', '..')
            or PurePosixPath(path).suffix.lower() not in ('.png', '.jpg', '.jpeg')
            or len(path) > 255):
        raise ValueError('Path gambar tidak valid')
    return path


def make_image(path, content):
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/png'
    elif content.startswith(b'\xff\xd8\xff'):
        mime = 'image/jpeg'
    else:
        raise ValueError('Format gambar harus PNG atau JPEG')
    return dict(path=image_url(path), content=content, mime_type=mime,
                sha256=hashlib.sha256(content).hexdigest())


def migrate_image_schema(cursor):
    cursor.execute('''CREATE TABLE IF NOT EXISTS inspection_images (
        path VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin PRIMARY KEY,
        technician_id INT NULL,
        mime_type VARCHAR(32) NOT NULL,
        content LONGBLOB NOT NULL,
        sha256 CHAR(64) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY image_technician (technician_id)
    ) ENGINE=InnoDB''')


def save_images(cursor, images, technician_id):
    for image in images:
        cursor.execute('''INSERT INTO inspection_images
            (path, technician_id, mime_type, content, sha256)
            VALUES (%s,%s,%s,%s,%s)''',
            (image['path'], technician_id, image['mime_type'],
             image['content'], image['sha256']))


def read_image(conn, path, technician_id=None, admin=False):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''SELECT i.content, i.mime_type, i.sha256 FROM inspection_images i
            WHERE i.path=%s AND (%s OR i.technician_id=%s
              OR EXISTS (SELECT 1 FROM detections d WHERE d.technician_id=%s
                         AND (d.source_image_path=i.path OR d.image_path=i.path))
              OR EXISTS (SELECT 1 FROM detection_history h WHERE h.technician_id=%s
                         AND (h.original_image_path=i.path OR h.image_path=i.path)))''',
            (image_url(path), admin, technician_id, technician_id, technician_id))
        return cursor.fetchone()
    finally:
        cursor.close()


def create_image_routes(get_connection):
    blueprint = Blueprint('images', __name__)

    @blueprint.route('/images/<folder>/<filename>')
    def show(folder, filename):
        if session.get('role') not in ('admin', 'technician'):
            return redirect('/login')
        try:
            path = image_url('/images/' + folder + '/' + filename)
        except ValueError:
            abort(404)
        conn = get_connection()
        try:
            image = read_image(conn, path, session.get('user_id'), session['role'] == 'admin')
        finally:
            conn.close()
        if not image:
            abort(404)
        response = send_file(io.BytesIO(bytes(image['content'])),
                             mimetype=image['mime_type'], etag=image['sha256'],
                             download_name=filename, conditional=True, max_age=0)
        response.headers['Cache-Control'] = 'private, no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.vary.add('Cookie')
        return response

    return blueprint
