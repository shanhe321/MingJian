#!/usr/bin/env python3
"""插入 PCB 检测场景和默认模型"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database.session import SessionLocal
from app.entity.db_models import DetectionScene, ModelVersion

MODEL_PATH = os.path.join(os.path.dirname(__file__), "runs/train/pcb_defect_v1/weights/best.pt")
db = SessionLocal()

# 场景
s = db.query(DetectionScene).filter(DetectionScene.name == "pcb_defect").first()
if not s:
    s = DetectionScene(name="pcb_defect", display_name="PCB 缺陷检测", category="industry",
        description="基于 YOLO11n 的 PCB 电路板缺陷检测",
        class_names=json.dumps(["missing_hole","mouse_bite","open_circuit","short","spur","spurious_copper"]),
        class_names_cn=json.dumps({"missing_hole":"漏孔","mouse_bite":"鼠咬","open_circuit":"开路","short":"短路","spur":"毛刺","spurious_copper":"多余铜"}),
        is_active=True)
    db.add(s); db.flush()
    print(f"场景已创建: id={s.id}")
else:
    print(f"场景已存在: id={s.id}")

# 模型版本
m = db.query(ModelVersion).filter(ModelVersion.scene_id == s.id, ModelVersion.is_default == True).first()
if not m:
    m = ModelVersion(scene_id=s.id, version="v1.0", model_name="PCB-Defect-YOLO11n", model_type="yolo11n",
        model_path=MODEL_PATH, is_default=True, status="active", file_size=os.path.getsize(MODEL_PATH),
        description="PCB 缺陷检测 YOLO11n v1.0")
    db.add(m); db.flush()
    print(f"模型版本已创建: id={m.id}")
else:
    print(f"模型版本已存在: id={m.id}")

db.commit(); db.close()
print("完成！")
