from ultralytics import YOLO
import torch

print("CUDA Available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

# Load model YOLOv8 Nano
model = YOLO("yolov8n.pt")

# Training
results = model.train(
    data="data.yaml",
    epochs=100,       # FIX: 30 -> 100
    imgsz=640,
    batch=16,
    patience=30,      # FIX: 10 -> 30, supaya tidak berhenti dini sebelum sempat mencapai epoch ke-100
    workers=2,
    amp=True,
    cache=True,
    device=0 if torch.cuda.is_available() else "cpu",
    project="PCB_Project",
    name="YOLOv8n_PCB"
)

print("Training selesai")