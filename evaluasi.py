from ultralytics import YOLO

model = YOLO("best.pt")

metrics = model.val(data="data.yaml", split="test")

print("mAP50:", metrics.box.map50)
print("mAP50-95:", metrics.box.map)