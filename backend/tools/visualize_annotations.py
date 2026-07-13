from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "pcb_defect"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "pcb_defect_visual_checks"
CLASS_NAMES = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]
COLORS = [
    (230, 57, 70),
    (29, 185, 84),
    (30, 144, 255),
    (255, 159, 28),
    (155, 93, 229),
    (0, 180, 216),
]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_args():
    parser = argparse.ArgumentParser(description="Visualize YOLO annotations.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="YOLO dataset directory.")
    parser.add_argument("--split", default="train", choices=["train", "val", "test"], help="Split to sample.")
    parser.add_argument("--count", type=int, default=16, help="Number of images to visualize.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser.parse_args()


def find_image(image_dir: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        path = image_dir / f"{stem}{ext}"
        if path.exists():
            return path
    return None


def draw_labels(image_path: Path, label_path: Path, output_path: Path):
    font = ImageFont.load_default()
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        width, height = img.size
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            cid = int(parts[0])
            x, y, w, h = [float(v) for v in parts[1:]]
            xmin = int((x - w / 2) * width)
            ymin = int((y - h / 2) * height)
            xmax = int((x + w / 2) * width)
            ymax = int((y + h / 2) * height)
            color = COLORS[cid % len(COLORS)]
            draw.rectangle([xmin, ymin, xmax, ymax], outline=color, width=3)
            text = f"{cid}:{CLASS_NAMES[cid]}"
            text_box = draw.textbbox((xmin, max(0, ymin - 12)), text, font=font)
            draw.rectangle(text_box, fill=color)
            draw.text((text_box[0], text_box[1]), text, fill=(255, 255, 255), font=font)
        img.save(output_path, quality=95)


def main():
    args = parse_args()
    dataset = Path(args.dataset)
    output_dir = Path(args.output) / args.split
    output_dir.mkdir(parents=True, exist_ok=True)

    label_dir = dataset / "labels" / args.split
    image_dir = dataset / "images" / args.split
    labels = sorted(label_dir.glob("*.txt"))
    random.Random(args.seed).shuffle(labels)

    count = 0
    for label_path in labels:
        image_path = find_image(image_dir, label_path.stem)
        if image_path is None:
            continue
        draw_labels(image_path, label_path, output_dir / f"{label_path.stem}.jpg")
        count += 1
        if count >= args.count:
            break

    print(f"saved {count} visualized images to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
