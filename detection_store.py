"""Persist inspections using the current smartpcb_db schema."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from inspection_workflow import track_detection
from image_store import save_images


@lru_cache(maxsize=4)
def _model_digest(path, size, modified):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def save_detection(conn, *, technician_id, pcb_id, source_image, result_image,
                   defect_type, status, objects, width, height,
                   model_path, images=()):
    """Commit images, inspection, objects and history in one transaction."""
    model_file = Path(model_path).resolve()
    stat = model_file.stat()
    digest = _model_digest(str(model_file), stat.st_size, stat.st_mtime_ns)
    cursor = conn.cursor()
    try:
        save_images(cursor, images, technician_id)
        cursor.execute(
            """INSERT INTO detections
               (technician_id, pcb_id, source_image_path, image_path,
                result_image_path, defect_type, status, object_count,
                model_sha256, image_width, image_height)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (technician_id, pcb_id, source_image, result_image, result_image,
             defect_type, status, len(objects), digest, width, height),
        )
        detection_id = cursor.lastrowid
        if objects:
            cursor.executemany(
                """INSERT INTO detection_objects
                   (detection_id, class_id, defect_type, x1,y1,x2,y2)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                [(detection_id, obj['class_id'], obj['class'],
                  obj['x1'], obj['y1'], obj['x2'], obj['y2']) for obj in objects],
            )
        cursor.execute(
            """INSERT INTO detection_history
               (detection_id, technician_id, original_image_path, image_path,
                defect_type, defect_types, objects_json, object_count,
                status, model_name, created_at)
               SELECT id, technician_id, source_image_path, image_path,
                      defect_type, %s, %s, object_count, status, %s,
                      created_at FROM detections WHERE id = %s""",
            (json.dumps(sorted({obj['class'] for obj in objects})),
             json.dumps(objects), model_file.name, detection_id),
        )
        track_detection(cursor, technician_id, pcb_id, detection_id)
        conn.commit()
        return detection_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
