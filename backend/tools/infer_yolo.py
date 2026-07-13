from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = PROJECT_ROOT / "runs" / "train" / "pcb_defect_quick_smoke" / "weights" / "best.pt"
DEFAULT_SOURCE = PROJECT_ROOT / "datasets" / "pcb_defect" / "images" / "test"
DEFAULT_OUTPUT = PROJECT_ROOT / "runs" / "predict"


def parse_args():
    parser = argparse.ArgumentParser(description="Run YOLOv11 inference with a trained PCB defect checkpoint.")
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="Path to best.pt or last.pt.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Image, directory, or glob source.")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold.")
    parser.add_argument("--device", default="0", help="CUDA device id, or cpu.")
    parser.add_argument("--name", default="pcb_defect_infer", help="Prediction run name.")
    parser.add_argument("--max-det", type=int, default=300, help="Maximum detections per image.")
    return parser.parse_args()


def main():
    from ultralytics import YOLO
    import torch

    args = parse_args()
    device = args.device
    if device != "cpu" and not torch.cuda.is_available():
        device = "cpu"

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"[ERROR] model not found: {model_path}")
        return 1

    model = YOLO(str(model_path))
    results = model.predict(
        source=args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        device=device,
        project=str(DEFAULT_OUTPUT),
        name=args.name,
        exist_ok=True,
        save=True,
        max_det=args.max_det,
    )

    save_dir = Path(results[0].save_dir) if results else DEFAULT_OUTPUT / args.name
    print(f"prediction_dir: {save_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
