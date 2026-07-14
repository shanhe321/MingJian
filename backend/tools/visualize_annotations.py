from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTED_DEFAULT = PROJECT_ROOT / "datasets" / "rsod" / "yolo_dataset"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "rsod" / "vis_output"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (128, 255, 0), (255, 128, 0),
    (0, 128, 255), (128, 0, 255), (255, 255, 128), (128, 255, 255),
    (255, 128, 255), (0, 128, 128), (128, 0, 128), (128, 128, 0),
    (64, 255, 64), (255, 64, 64), (64, 64, 255), (255, 200, 0),
]
CLASS_NAMES = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Visualize YOLO annotations.")
    parser.add_argument("--dataset", default=str(default_dataset_dir()))
    parser.add_argument("--split", default="train", choices=["train", "val", "test"])
    parser.add_argument("--count", type=int, default=16)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def find_image(image_dir: Path, stem: str) -> Path | None:
    for extension in IMAGE_EXTS:
        path = image_dir / f"{stem}{extension}"
        if path.exists():
            return path
    return None


def draw_labels(image_path: Path, label_path: Path, output_path: Path):
    image = cv2.imread(str(image_path))
    if image is None:
        return
    class_names = {index: name for index, name in enumerate(CLASS_NAMES)}
    annotated = draw_yolo_annotations(image, label_path, class_names)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), annotated)


def default_dataset_dir() -> Path:
    if DOCUMENTED_DEFAULT.exists():
        return DOCUMENTED_DEFAULT
    for yaml_path in sorted((PROJECT_ROOT / "datasets").glob("*/data.yaml")):
        return yaml_path.parent
    return DOCUMENTED_DEFAULT


def load_class_names(dataset_dir: str | os.PathLike[str]) -> dict[int, str]:
    yaml_path = Path(dataset_dir) / "data.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml

        names = (yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}).get("names", {})
        if isinstance(names, list):
            return {index: str(name) for index, name in enumerate(names)}
        if isinstance(names, dict):
            return {int(index): str(name) for index, name in names.items()}
    except (ImportError, TypeError, ValueError):
        pass
    return {}


def draw_yolo_annotations(
    image: np.ndarray,
    label_file: str | os.PathLike[str],
    class_names: dict[int, str],
    thickness: int = 2,
    font_scale: float = 0.6,
) -> np.ndarray:
    image_height, image_width = image.shape[:2]
    label_path = Path(label_file)
    if not label_path.exists():
        return image
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = map(float, parts[1:])
        except ValueError:
            continue
        x1 = max(0, min(int((x_center - width / 2) * image_width), image_width - 1))
        y1 = max(0, min(int((y_center - height / 2) * image_height), image_height - 1))
        x2 = max(0, min(int((x_center + width / 2) * image_width), image_width - 1))
        y2 = max(0, min(int((y_center + height / 2) * image_height), image_height - 1))
        color = COLORS[class_id % len(COLORS)]
        label = class_names.get(class_id, f"class_{class_id}")
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
        (text_width, text_height), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1
        )
        label_y = max(y1, text_height + 10)
        cv2.rectangle(
            image,
            (x1, label_y - text_height - 10),
            (x1 + text_width, label_y),
            color,
            -1,
        )
        cv2.putText(
            image,
            label,
            (x1, label_y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return image


def collect_image_label_pairs(
    dataset_dir: str | os.PathLike[str], splits: list[str] | None = None
) -> list[tuple[str, str, str, str]]:
    dataset_path = Path(dataset_dir)
    pairs = []
    for split in splits or ["train", "val", "test"]:
        image_dir = dataset_path / "images" / split
        label_dir = dataset_path / "labels" / split
        if not image_dir.exists():
            continue
        for image_path in sorted(image_dir.iterdir()):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTS:
                pairs.append(
                    (str(image_path), str(label_dir / f"{image_path.stem}.txt"), split, image_path.name)
                )
    return pairs


def visualize_random_samples(
    dataset_dir: str,
    output_dir: str | None = None,
    count: int = 5,
    splits: list[str] | None = None,
    class_names: dict[int, str] | None = None,
) -> None:
    class_names = class_names if class_names is not None else load_class_names(dataset_dir)
    pairs = collect_image_label_pairs(dataset_dir, splits)
    if not pairs:
        print("[错误] 未找到任何图像-标注配对文件")
        return
    samples = random.sample(pairs, min(count, len(pairs)))
    print(f"\n共找到 {len(pairs)} 张图像，随机抽样 {len(samples)} 张进行可视化\n")
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    for image_path, label_path, split, filename in samples:
        image = cv2.imread(image_path)
        if image is None:
            print(f"  [跳过] 无法读取图像：{image_path}")
            continue
        annotated = draw_yolo_annotations(image, label_path, class_names)
        cv2.putText(
            annotated,
            f"split: {split} | file: {filename}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        if output_dir:
            output_path = Path(output_dir) / f"vis_{split}_{filename}"
            cv2.imwrite(str(output_path), annotated)
            print(f"  [保存] {output_path}")
        else:
            cv2.imshow(f"[{split}] {filename}", annotated)
            key = cv2.waitKey(0) & 0xFF
            cv2.destroyAllWindows()
            if key == ord("q"):
                break


def visualize_single_image(
    dataset_dir: str,
    image_relpath: str,
    output_path: str | None = None,
    class_names: dict[int, str] | None = None,
) -> None:
    parts = image_relpath.replace("\\", "/").split("/")
    if len(parts) < 2:
        print("[错误] 请指定包含 split 的路径，如 train/000001.jpg")
        return
    split, filename = parts[0], parts[-1]
    image_path = Path(dataset_dir) / "images" / split / filename
    label_path = Path(dataset_dir) / "labels" / split / f"{image_path.stem}.txt"
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"[错误] 无法读取图像：{image_path}")
        return
    annotated = draw_yolo_annotations(
        image, label_path, class_names or load_class_names(dataset_dir)
    )
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(destination), annotated)
        print(f"已保存到：{destination}")
    else:
        cv2.imshow(f"[{split}] {filename}", annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def generate_overview_grid(
    dataset_dir: str,
    output_path: str,
    grid_size: tuple[int, int] = (4, 4),
    splits: list[str] | None = None,
    class_names: dict[int, str] | None = None,
) -> None:
    pairs = collect_image_label_pairs(dataset_dir, splits)
    if not pairs:
        print("[错误] 未找到任何图像-标注配对文件")
        return
    rows, columns = grid_size
    samples = random.sample(pairs, min(rows * columns, len(pairs)))
    thumb_width, thumb_height = 400, 300
    grid = np.zeros((rows * thumb_height, columns * thumb_width, 3), dtype=np.uint8)
    names = class_names if class_names is not None else load_class_names(dataset_dir)
    for index, (image_path, label_path, split, filename) in enumerate(samples):
        image = cv2.imread(image_path)
        if image is None:
            continue
        annotated = draw_yolo_annotations(image, label_path, names, 1, 0.4)
        thumbnail = cv2.resize(annotated, (thumb_width, thumb_height))
        cv2.putText(
            thumbnail,
            f"{split}/{filename[:20]}",
            (5, 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        row, column = divmod(index, columns)
        grid[
            row * thumb_height : (row + 1) * thumb_height,
            column * thumb_width : (column + 1) * thumb_width,
        ] = thumbnail
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destination), grid)
    print(f"概览网格图已保存到：{destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLO 数据集标注可视化工具")
    parser.add_argument("--dataset", "-d", default=str(default_dataset_dir()))
    parser.add_argument("--count", "-n", type=int, default=5)
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--image", "-i", default=None)
    parser.add_argument("--grid", action="store_true")
    parser.add_argument("--splits", nargs="+", default=["train", "val"])
    args = parser.parse_args()
    if not Path(args.dataset).exists():
        print(f"[错误] 数据集目录不存在：{args.dataset}")
        return 1
    class_names = load_class_names(args.dataset)
    print(f"加载类别：{class_names}" if class_names else "[警告] 未找到 data.yaml 中的类别")
    if args.grid:
        output = args.output or str(DEFAULT_OUTPUT_DIR / "overview.jpg")
        generate_overview_grid(args.dataset, output, splits=args.splits, class_names=class_names)
    elif args.image:
        visualize_single_image(args.dataset, args.image, args.output, class_names)
    else:
        visualize_random_samples(args.dataset, args.output, args.count, args.splits, class_names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
