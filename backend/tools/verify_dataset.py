#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTED_DEFAULT = PROJECT_ROOT / "datasets" / "rsod" / "yolo_dataset"


def default_dataset_dir() -> Path:
    if DOCUMENTED_DEFAULT.exists():
        return DOCUMENTED_DEFAULT
    for yaml_path in sorted((PROJECT_ROOT / "datasets").glob("*/data.yaml")):
        return yaml_path.parent
    return DOCUMENTED_DEFAULT


def load_yaml_classes(dataset_dir: Path) -> dict[int, str]:
    yaml_path = dataset_dir / "data.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        names = data.get("names", {})
        if isinstance(names, list):
            return {index: str(name) for index, name in enumerate(names)}
        if isinstance(names, dict):
            return {int(index): str(name) for index, name in names.items()}
    except (ImportError, ValueError, TypeError):
        pass

    classes: dict[int, str] = {}
    in_names = False
    for raw_line in yaml_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("names:"):
            in_names = True
            continue
        if not in_names:
            continue
        if stripped.startswith("-"):
            classes[len(classes)] = stripped[1:].strip().strip("'\"")
        elif ":" in stripped and stripped.split(":", 1)[0].strip().isdigit():
            key, value = stripped.split(":", 1)
            classes[int(key.strip())] = value.strip().strip("'\"")
        elif stripped and not raw_line.startswith((" ", "\t")):
            break
    return classes


def verify_dataset(dataset_dir: str | os.PathLike[str]) -> dict:
    dataset_path = Path(dataset_dir).resolve()
    results = {
        "total_images": 0,
        "total_labels": 0,
        "total_annotations": 0,
        "missing_labels": [],
        "missing_images": [],
        "empty_labels": 0,
        "invalid_format": [],
        "out_of_range": [],
        "class_distribution": {},
        "class_names": load_yaml_classes(dataset_path),
        "bbox_stats": {
            "total": 0,
            "avg_width": 0.0,
            "avg_height": 0.0,
            "max_width": 0.0,
            "max_height": 0.0,
            "min_width": float("inf"),
            "min_height": float("inf"),
            "small_boxes": 0,
            "large_boxes": 0,
        },
        "split_stats": {},
        "has_warnings": False,
    }
    bbox_widths: list[float] = []
    bbox_heights: list[float] = []

    if not results["class_names"]:
        results["invalid_format"].append("data.yaml 缺少有效的 names 定义")

    for split in ("train", "val", "test"):
        image_dir = dataset_path / "images" / split
        label_dir = dataset_path / "labels" / split
        split_result = {
            "images": 0,
            "labels": 0,
            "annotations": 0,
            "missing_labels": 0,
            "missing_images": 0,
            "class_distribution": {},
        }
        if not image_dir.exists() or not label_dir.exists():
            if split != "test":
                missing = image_dir if not image_dir.exists() else label_dir
                results["invalid_format"].append(f"缺少目录: {missing}")
            results["split_stats"][split] = split_result
            continue

        image_files = {
            path.stem for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS
        }
        label_files = {
            path.stem for path in label_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".txt"
        }
        missing_labels = sorted(image_files - label_files)
        missing_images = sorted(label_files - image_files)
        split_result.update(
            images=len(image_files),
            labels=len(label_files),
            missing_labels=len(missing_labels),
            missing_images=len(missing_images),
        )
        results["missing_labels"].extend(f"{split}/{name}" for name in missing_labels)
        results["missing_images"].extend(f"{split}/{name}" for name in missing_images)
        results["total_images"] += len(image_files)
        results["total_labels"] += len(label_files)

        for label_file in sorted(label_dir.glob("*.txt")):
            content = label_file.read_text(encoding="utf-8").strip()
            if not content:
                results["empty_labels"] += 1
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                parts = line.split()
                location = f"{split}/{label_file.name}:{line_number}"
                if len(parts) != 5:
                    results["invalid_format"].append(
                        f"{location} (期望 5 个值, 实际 {len(parts)})"
                    )
                    continue
                try:
                    class_id = int(parts[0])
                except ValueError:
                    results["invalid_format"].append(f"{location} (class_id 非整数)")
                    continue
                try:
                    x_center, y_center, width, height = (float(value) for value in parts[1:])
                except ValueError:
                    results["invalid_format"].append(f"{location} (坐标值非浮点数)")
                    continue
                if class_id not in results["class_names"]:
                    results["invalid_format"].append(f"{location} (无效 class_id={class_id})")
                if width <= 0 or height <= 0:
                    results["invalid_format"].append(f"{location} (width/height 必须大于 0)")
                for field, value in zip(
                    ("x_center", "y_center", "width", "height"),
                    (x_center, y_center, width, height),
                ):
                    if not 0.0 <= value <= 1.0:
                        results["out_of_range"].append(f"{location} {field}={value:.6f}")
                        break

                results["class_distribution"][class_id] = (
                    results["class_distribution"].get(class_id, 0) + 1
                )
                split_result["class_distribution"][class_id] = (
                    split_result["class_distribution"].get(class_id, 0) + 1
                )
                results["total_annotations"] += 1
                split_result["annotations"] += 1
                bbox_widths.append(width)
                bbox_heights.append(height)

        results["split_stats"][split] = split_result

    bbox = results["bbox_stats"]
    if bbox_widths:
        bbox["total"] = len(bbox_widths)
        bbox["avg_width"] = sum(bbox_widths) / len(bbox_widths)
        bbox["avg_height"] = sum(bbox_heights) / len(bbox_heights)
        bbox["max_width"] = max(bbox_widths)
        bbox["max_height"] = max(bbox_heights)
        bbox["min_width"] = min(bbox_widths)
        bbox["min_height"] = min(bbox_heights)
        bbox["small_boxes"] = sum(
            1 for width, height in zip(bbox_widths, bbox_heights) if width * height < 0.001
        )
        bbox["large_boxes"] = sum(
            1 for width, height in zip(bbox_widths, bbox_heights) if width * height > 0.5
        )
    else:
        bbox["min_width"] = 0.0
        bbox["min_height"] = 0.0

    counts = list(results["class_distribution"].values())
    severe_imbalance = bool(counts and min(counts) > 0 and max(counts) / min(counts) > 10)
    results["has_warnings"] = bool(
        results["missing_labels"]
        or results["missing_images"]
        or results["invalid_format"]
        or results["out_of_range"]
        or severe_imbalance
    )
    return results


def print_report(results: dict) -> None:
    print("\n" + "=" * 70)
    print("              YOLO 数据集验证报告")
    print("=" * 70)
    print("\n  [总体统计]")
    print(f"    图像总数：{results['total_images']}")
    print(f"    标注文件数：{results['total_labels']}")
    print(f"    标注目标数：{results['total_annotations']}")
    print(f"    空标注文件：{results['empty_labels']}")
    print("\n  [Split 统计]")
    for split in ("train", "val", "test"):
        stats = results["split_stats"].get(split, {})
        print(
            f"    {split}: {stats.get('images', 0)} 图像, "
            f"{stats.get('labels', 0)} 标注, {stats.get('annotations', 0)} 目标"
        )

    for title, key in (
        ("缺少标注文件", "missing_labels"),
        ("缺少图像文件", "missing_images"),
        ("格式错误", "invalid_format"),
        ("坐标越界", "out_of_range"),
    ):
        items = results[key]
        if items:
            print(f"\n  [警告] {title} ({len(items)} 处)：")
            for item in items[:5]:
                print(f"    - {item}")

    print("\n  [类别分布]")
    distribution = results["class_distribution"]
    max_count = max(distribution.values(), default=0)
    total = results["total_annotations"] or 1
    for class_id in sorted(distribution):
        count = distribution[class_id]
        name = results["class_names"].get(class_id, f"class_{class_id}")
        bar_length = int(count / max_count * 40) if max_count else 0
        print(
            f"    {class_id:2d}. {name:18s} {count:6d} 个 "
            f"({count / total * 100:5.2f}%) {'█' * bar_length}{'░' * (40 - bar_length)}"
        )

    bbox = results["bbox_stats"]
    print("\n  [边界框统计]")
    print(f"    边界框总数：{bbox['total']}")
    if bbox["total"]:
        print(f"    平均宽度/高度：{bbox['avg_width']:.4f} / {bbox['avg_height']:.4f}")
        print(f"    小目标（面积<0.001）：{bbox['small_boxes']}")
        print(f"    大目标（面积>0.5）：{bbox['large_boxes']}")
    print("\n" + "─" * 70)
    print("  结果：⚠ 数据集存在问题或警告" if results["has_warnings"] else "  结果：✓ 数据集验证通过，可以开始训练")
    print("─" * 70 + "\n")


def main() -> int:
    dataset_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else default_dataset_dir()
    if not dataset_dir.exists():
        print(f"[错误] 数据集目录不存在: {dataset_dir}")
        return 1
    results = verify_dataset(dataset_dir)
    print_report(results)
    return 1 if results["has_warnings"] else 0


if __name__ == "__main__":
    sys.exit(main())
