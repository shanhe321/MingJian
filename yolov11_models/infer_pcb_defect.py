from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = SCRIPT_DIR / "weights" / "best.pt"
DEFAULT_OUTPUT = SCRIPT_DIR / "results" / "predict"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run YOLO11 PCB defect inference on one image, a directory, or a glob pattern."
    )
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="Path to best.pt or another YOLO checkpoint.")
    parser.add_argument(
        "--source",
        required=True,
        help="Input image path, directory path, or glob pattern such as 'images/*.jpg'.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Directory for annotated images and result files.")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold.")
    parser.add_argument("--iou", type=float, default=0.7, help="NMS IoU threshold.")
    parser.add_argument("--device", default="0", help="CUDA device id, or cpu.")
    parser.add_argument("--max-det", type=int, default=300, help="Maximum detections per image.")
    return parser.parse_args()


def to_builtin(value):
    if hasattr(value, "item"):
        return value.item()
    return value


def collect_detections(results) -> list[dict]:
    images: list[dict] = []
    for result in results:
        image_path = str(result.path)
        image_name = Path(image_path).name
        height, width = result.orig_shape
        image_record = {
            "image": image_path,
            "image_name": image_name,
            "width": int(width),
            "height": int(height),
            "detections": [],
        }

        names = result.names
        if result.boxes is not None:
            xyxy = result.boxes.xyxy.cpu().tolist()
            confs = result.boxes.conf.cpu().tolist()
            classes = result.boxes.cls.cpu().tolist()
            for box, conf, cls in zip(xyxy, confs, classes):
                x1, y1, x2, y2 = [float(v) for v in box]
                class_id = int(to_builtin(cls))
                image_record["detections"].append(
                    {
                        "class_id": class_id,
                        "class_name": str(names.get(class_id, class_id)),
                        "confidence": float(conf),
                        "bbox_xyxy": [x1, y1, x2, y2],
                        "bbox_xywh": [x1, y1, x2 - x1, y2 - y1],
                    }
                )

        images.append(image_record)
    return images


def write_json(images: list[dict], output_dir: Path) -> Path:
    json_path = output_dir / "detections.json"
    json_path.write_text(json.dumps({"images": images}, indent=2), encoding="utf-8")
    return json_path


def write_csv(images: list[dict], output_dir: Path) -> Path:
    csv_path = output_dir / "detections.csv"
    fields = [
        "image",
        "image_name",
        "image_width",
        "image_height",
        "class_id",
        "class_name",
        "confidence",
        "x1",
        "y1",
        "x2",
        "y2",
        "bbox_width",
        "bbox_height",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for image in images:
            for det in image["detections"]:
                x1, y1, x2, y2 = det["bbox_xyxy"]
                _, _, box_w, box_h = det["bbox_xywh"]
                writer.writerow(
                    {
                        "image": image["image"],
                        "image_name": image["image_name"],
                        "image_width": image["width"],
                        "image_height": image["height"],
                        "class_id": det["class_id"],
                        "class_name": det["class_name"],
                        "confidence": det["confidence"],
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "bbox_width": box_w,
                        "bbox_height": box_h,
                    }
                )
    return csv_path


def main() -> int:
    from ultralytics import YOLO
    import torch

    args = parse_args()
    model_path = Path(args.model)
    output_dir = Path(args.output)

    if not model_path.exists():
        print(f"[ERROR] model not found: {model_path}", file=sys.stderr)
        return 1

    device = args.device
    if device != "cpu" and not torch.cuda.is_available():
        print("[WARN] CUDA is not available; falling back to CPU.")
        device = "cpu"

    output_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(model_path))
    results = model.predict(
        source=args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        device=device,
        max_det=args.max_det,
        project=str(output_dir.parent),
        name=output_dir.name,
        exist_ok=True,
        save=True,
        verbose=False,
    )

    save_dir = Path(results[0].save_dir) if results else output_dir
    images = collect_detections(results)
    json_path = write_json(images, save_dir)
    csv_path = write_csv(images, save_dir)
    detection_count = sum(len(image["detections"]) for image in images)

    print(f"annotated_images_dir: {save_dir}")
    print(f"detections_json: {json_path}")
    print(f"detections_csv: {csv_path}")
    print(f"images: {len(images)}")
    print(f"detections: {detection_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
