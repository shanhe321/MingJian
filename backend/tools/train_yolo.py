from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT_ROOT / "datasets" / "pcb_defect" / "data.yaml"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "runs" / "train"
CLASS_NAMES = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_args():
    parser = argparse.ArgumentParser(description="Train YOLOv11 on the PCB defect dataset.")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Path to YOLO data.yaml.")
    parser.add_argument("--model", default="yolo11n.pt", help="Base model or checkpoint path.")
    parser.add_argument("--epochs", type=int, default=5, help="Training epochs.")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size.")
    parser.add_argument("--batch", type=int, default=16, help="Batch size.")
    parser.add_argument("--device", default="0", help="CUDA device id, or cpu.")
    parser.add_argument("--workers", type=int, default=4, help="Dataloader workers.")
    parser.add_argument("--save-period", type=int, default=1, help="Save checkpoint every N epochs. Use -1 to disable periodic saves.")
    parser.add_argument("--patience", type=int, default=100, help="Early stopping patience in epochs.")
    parser.add_argument("--name", default="", help="Run name under backend/runs/train.")
    parser.add_argument("--quick", action="store_true", help="Create and train on a small subset for a fast smoke test.")
    parser.add_argument("--quick-train", type=int, default=240, help="Quick mode train image count.")
    parser.add_argument("--quick-val", type=int, default=60, help="Quick mode val image count.")
    parser.add_argument("--quick-test", type=int, default=30, help="Quick mode test image count.")
    return parser.parse_args()


def find_image(image_dir: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        path = image_dir / f"{stem}{ext}"
        if path.exists():
            return path
    return None


def write_data_yaml(dataset_dir: Path):
    lines = [
        f"path: {dataset_dir.resolve().as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        f"nc: {len(CLASS_NAMES)}",
        "names:",
    ]
    lines.extend(f"  {idx}: {name}" for idx, name in enumerate(CLASS_NAMES))
    (dataset_dir / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_quick_dataset(data_yaml: Path, train_count: int, val_count: int, test_count: int) -> Path:
    full_dataset = data_yaml.parent
    quick_dataset = PROJECT_ROOT / "datasets" / "pcb_defect_quick"
    if quick_dataset.exists():
        shutil.rmtree(quick_dataset)

    counts = {"train": train_count, "val": val_count, "test": test_count}
    for split, count in counts.items():
        (quick_dataset / "images" / split).mkdir(parents=True, exist_ok=True)
        (quick_dataset / "labels" / split).mkdir(parents=True, exist_ok=True)
        label_paths = sorted((full_dataset / "labels" / split).glob("*.txt"))[:count]
        for label_path in label_paths:
            image_path = find_image(full_dataset / "images" / split, label_path.stem)
            if image_path is None:
                continue
            shutil.copy2(image_path, quick_dataset / "images" / split / image_path.name)
            shutil.copy2(label_path, quick_dataset / "labels" / split / label_path.name)

    write_data_yaml(quick_dataset)
    return quick_dataset / "data.yaml"


def main():
    from ultralytics import YOLO
    import torch

    args = parse_args()
    data_yaml = Path(args.data).resolve()
    if args.quick:
        data_yaml = make_quick_dataset(data_yaml, args.quick_train, args.quick_val, args.quick_test)

    run_name = args.name
    if not run_name:
        suffix = "quick" if args.quick else "full"
        run_name = f"pcb_defect_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)
    device = args.device
    if device != "cpu" and not torch.cuda.is_available():
        device = "cpu"

    print("=" * 70)
    print("YOLOv11 training")
    print("=" * 70)
    print(f"data: {data_yaml}")
    print(f"model: {args.model}")
    print(f"epochs: {args.epochs}")
    print(f"imgsz: {args.imgsz}")
    print(f"batch: {args.batch}")
    print(f"device: {device}")
    print(f"save_period: {args.save_period}")
    print(f"patience: {args.patience}")
    print(f"name: {run_name}")

    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=args.workers,
        project=str(DEFAULT_RUNS_DIR),
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
