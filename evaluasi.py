from ultralytics import YOLO

model = YOLO(
    "runs/detect/PCB_Project/YOLOv8n_PCB-5/weights/best.pt"
)

metrics = model.val()

print("mAP50:", metrics.box.map50)
print("mAP50-95:", metrics.box.map)