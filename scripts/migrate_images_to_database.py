"""Move legacy inspection images into MySQL; verify bytes before any file cleanup."""
import argparse
import json
from pathlib import Path
import re
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db import get_db
from image_store import IMAGE_FOLDERS, image_url, make_image, migrate_image_schema


def migrate(output):
    files = [p for folder in IMAGE_FOLDERS
             for p in (ROOT / 'static' / folder).glob('*')
             if p.is_file() and p.suffix.lower() in ('.png', '.jpg', '.jpeg')]
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT @@max_allowed_packet AS packet')
        packet = cursor.fetchone()['packet']
        if files and max(p.stat().st_size for p in files) + 65536 >= packet:
            raise RuntimeError('max_allowed_packet terlalu kecil untuk gambar; gunakan minimal 64M.')
        migrate_image_schema(cursor)
        conn.commit()
        rows = {}
        references = {}
        owners = {}
        for table, columns in (
            ('detections', ('source_image_path', 'image_path', 'result_image_path')),
            ('detection_history', ('original_image_path', 'image_path')),
        ):
            cursor.execute('SELECT id,technician_id,' + ','.join(columns) + ' FROM ' + table)
            rows[table] = cursor.fetchall()
            references[table] = columns
            for row in rows[table]:
                for column in columns:
                    path = row[column]
                    if not path:
                        continue
                    try:
                        name = Path(image_url(path)).name
                    except ValueError:
                        continue
                    name = re.sub(r'^result_', '', name)
                    if row['technician_id'] is not None:
                        owners.setdefault(name, set()).add(row['technician_id'])
        manifest = []
        for index, file in enumerate(files, 1):
            assert file.resolve().is_relative_to((ROOT / 'static').resolve())
            asset = make_image('/images/' + file.parent.name + '/' + file.name, file.read_bytes())
            basename = re.sub(r'^(?:result_|resize_|normalize_|feature_|crop_\d+_)', '', file.name)
            candidates = owners.get(basename, set())
            owner = next(iter(candidates)) if len(candidates) == 1 else None
            cursor.execute('SELECT sha256 FROM inspection_images WHERE path=%s', (asset['path'],))
            saved = cursor.fetchone()
            if saved:
                if saved['sha256'] != asset['sha256']:
                    raise RuntimeError('Isi gambar berbeda dengan database: ' + str(file))
            else:
                cursor.execute('''INSERT INTO inspection_images
                    (path,technician_id,mime_type,content,sha256) VALUES (%s,%s,%s,%s,%s)''',
                    (asset['path'], owner, asset['mime_type'], asset['content'], asset['sha256']))
                conn.commit()
            cursor.execute('''SELECT SHA2(content,256) AS digest, OCTET_LENGTH(content) AS size
                              FROM inspection_images WHERE path=%s''', (asset['path'],))
            stored = cursor.fetchone()
            if stored['digest'] != asset['sha256'] or stored['size'] != len(asset['content']):
                raise RuntimeError('Verifikasi data gagal: ' + str(file))
            manifest.append(dict(file=str(file), path=asset['path'], sha256=asset['sha256'],
                                 size=len(asset['content'])))
            if index % 100 == 0:
                print('Verified', index, '/', len(files), flush=True)
        available = {item['path'] for item in manifest}
        cursor.execute('SELECT path FROM inspection_images')
        available.update(row['path'] for row in cursor.fetchall())
        missing = []
        for table, columns in references.items():
            source_column = 'source_image_path' if table == 'detections' else 'original_image_path'
            for row in rows[table]:
                # Recover original-image references for legacy rows where possible.
                if not row[source_column] and row['image_path']:
                    name = Path(row['image_path'].replace('\\', '/')).name
                    original = '/images/uploads/' + name.removeprefix('result_')
                    if name.startswith('result_') and original in available:
                        row[source_column] = original
                for column in columns:
                    if not row[column]:
                        continue
                    try:
                        path = image_url(row[column])
                    except ValueError:
                        missing.append(dict(table=table, id=row['id'], column=column, path=row[column]))
                        continue
                    if path not in available:
                        missing.append(dict(table=table, id=row['id'], column=column, path=row[column]))
                        continue
                    cursor.execute('UPDATE ' + table + ' SET ' + column + '=%s WHERE id=%s',
                                   (path, row['id']))
        conn.commit()
        output.mkdir(parents=True, exist_ok=True)
        report = dict(files=manifest, missing_references=missing,
                      verified_images=len(manifest), verified_bytes=sum(p['size'] for p in manifest))
        (output / 'migration.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Verified images:', len(manifest))
        print('Previously missing references:', len(missing))
        print('Verification manifest:', output / 'migration.json')
        return report
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'backup' / (
        'database_images_' + datetime.now().strftime('%Y%m%d_%H%M%S')))
    migrate(parser.parse_args().output)
