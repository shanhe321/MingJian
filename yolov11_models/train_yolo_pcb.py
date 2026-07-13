from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = SCRIPT_DIR / "data.yaml"
DEFAULT_RUNS_DIR = SCRIPT_DIR / "runs" / "train"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLO11 on the PCB defect dataset.")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Path to YOLO data.yaml.")
    parser.add_argument("--model", default="yolo11n.pt", help="Base model or checkpoint path.")
    parser.add_argument("--epochs", type=int, default=200, help="Training epochs.")
    parser.add_argument("--imgsz", type=int, default=640, help="Training image size.")
    parser.add_argument("--batch", type=int, default=32, help="Batch size.")
    parser.add_argument("--device", default="0", help="CUDA device id, or cpu.")
    parser.add_argument("--workers", type=int, default=8, help="Dataloader workers.")
    parser.add_argument("--save-period", type=int, default=1, help="Save checkpoint every N epochs.")
    parser.add_argument("--patience", type=int, default=200, help="Early stopping patience in epochs.")
    parser.add_argument("--project", default=str(DEFAULT_RUNS_DIR), help="Output project directory.")
    parser.add_argument("--name", default="", help="Run name.")
    return parser.parse_args()


def main() -> int:
    from ultralytics import YOLO
    import torch

    args = parse_args()
    data_yaml = Path(args.data).resolve()
    if not data_yaml.exists():
        print(f"[ERROR] data.yaml not found: {data_yaml}", file=sys.stderr)
        return 1

    device = args.device
    if device != "cpu" and not torch.cuda.is_available():
        print("[WARN] CUDA is not available; falling back to CPU.")
        device = "cpu"

    run_name = args.name or f"pcb_defect_yolo11n_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    model = YOLO(args.model)
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=args.workers,
        project=args.project,
        name=run_name,
        exist_ok=True,
        save_period=args.save_period,
        patience=args.patience,
        pretrained=True,
        verbose=True,
        plots=True,
    )

    save_dir = Path(results.save_dir)
    summary = {
        "data": str(data_yaml),
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": device,
        "workers": args.workers,
        "save_period": args.save_period,
        "patience": args.patience,
        "run_dir": str(save_dir),
        "best_pt": str(save_dir / "weights" / "best.pt"),
        "last_pt": str(save_dir / "weights" / "last.pt"),
    }
    (save_dir / "training_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
