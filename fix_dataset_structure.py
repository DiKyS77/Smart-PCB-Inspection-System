"""
Script untuk MENGECEK struktur folder dataset PCB Anda, dan otomatis
MERAPIKAN bila gambar & label .txt masih tercampur jadi satu folder.

Target struktur akhir (format standar yang dikenali Ultralytics YOLO):

    Smart-PCB-Inspection-System/
        train/
            images/   <- semua file .jpg/.png di sini
            labels/   <- semua file .txt di sini
        val/
            images/
            labels/
        test/
            images/
            labels/

Cara pakai:
1. Sesuaikan DATASET_ROOT di bawah kalau lokasi project Anda berbeda.
2. Jalankan: python fix_dataset_structure.py
3. Script ini AMAN dijalankan berkali-kali — kalau struktur sudah benar,
   split itu akan dilewati (tidak ada file yang dihapus/ditimpa).
"""

import os
import shutil

DATASET_ROOT = r"C:\xampp\htdocs\Smart-PCB-Inspection-System"
SPLITS = ["train", "val", "test"]
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
LABEL_EXT = ".txt"


def inspect_and_fix(split):
    split_path = os.path.join(DATASET_ROOT, split)
    if not os.path.isdir(split_path):
        print(f"[SKIP] Folder '{split}' tidak ditemukan di {DATASET_ROOT}")
        return

    images_dir = os.path.join(split_path, "images")
    labels_dir = os.path.join(split_path, "labels")

    # Kasus 1: struktur sudah benar (images/ dan labels/ sudah ada)
    if os.path.isdir(images_dir) and os.path.isdir(labels_dir):
        n_img = len([f for f in os.listdir(images_dir) if os.path.splitext(f)[1].lower() in IMAGE_EXTS])
        n_lbl = len([f for f in os.listdir(labels_dir) if f.endswith(LABEL_EXT)])
        print(f"[OK]   '{split}': sudah punya images/ ({n_img} file) & labels/ ({n_lbl} file). Tidak diubah.")
        if n_img != n_lbl:
            print(f"       -> PERHATIAN: jumlah gambar ({n_img}) dan label ({n_lbl}) tidak sama, "
                  f"cek apakah ada gambar tanpa label atau sebaliknya.")
        return

    # Kasus 2: gambar & label tercampur langsung di dalam folder split
    all_files = os.listdir(split_path)
    images = [f for f in all_files if os.path.splitext(f)[1].lower() in IMAGE_EXTS]
    labels = [f for f in all_files if f.endswith(LABEL_EXT)]

    if not images:
        print(f"[WARN] '{split}': tidak ada gambar ditemukan langsung di folder ini. "
              f"Cek manual, mungkin strukturnya berbeda dari yang diasumsikan script ini.")
        return

    print(f"[FIX]  '{split}': ditemukan {len(images)} gambar & {len(labels)} label tercampur. Merapikan...")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    for f in images:
        shutil.move(os.path.join(split_path, f), os.path.join(images_dir, f))
    for f in labels:
        shutil.move(os.path.join(split_path, f), os.path.join(labels_dir, f))

    print(f"[DONE] '{split}': sekarang punya images/ ({len(images)} file) & labels/ ({len(labels)} file).")
    if len(images) != len(labels):
        print(f"       -> PERHATIAN: jumlah gambar ({len(images)}) dan label ({len(labels)}) tidak sama, "
              f"cek apakah ada gambar tanpa label (artinya tidak punya anotasi defect).")


if __name__ == "__main__":
    print(f"Mengecek dataset di: {DATASET_ROOT}\n")
    for split in SPLITS:
        inspect_and_fix(split)
    print("\nSelesai. Pastikan data.yaml mengarah ke '<split>/images', contoh:")
    print("  train: train/images")
    print("  val: val/images")
    print("  test: test/images")