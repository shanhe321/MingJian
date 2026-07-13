import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "pcb_defect"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def load_yaml_classes(dataset_dir: Path) -> dict[int, str]:
    yaml_path = dataset_dir / "data.yaml"
    classes = {}
    in_names = False
    for raw_line in yaml_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.strip() == "names:":
            in_names = True
            continue
        if in_names:
            if not line.startswith("  "):
                break
            key, value = line.strip().split(":", 1)
            classes[int(key)] = value.strip().strip("'\"")
    return classes


def collect_images(path: Path) -> dict[str, Path]:
    return {item.stem: item for item in path.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTS}


def verify_label_file(label_path: Path, class_count: int):
    errors = []
    boxes = []
    class_counts = Counter()
    lines = label_path.read_text(encoding="utf-8").splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) != 5:
            errors.append(f"{label_path}: line {line_number} does not have 5 fields")
            continue

        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = [float(value) for value in parts[1:]]
        except ValueError:
            errors.append(f"{label_path}: line {line_number} contains non-numeric values")
            continue

        if class_id < 0 or class_id >= class_count:
            errors.append(f"{label_path}: line {line_number} invalid class id {class_id}")

        values = [x_center, y_center, width, height]
        if any(value < 0.0 or value > 1.0 for value in values):
            errors.append(f"{label_path}: line {line_number} coordinate out of [0, 1]")
        if width <= 0.0 or height <= 0.0:
            errors.append(f"{label_path}: line {line_number} invalid width/height")

        class_counts[class_id] += 1
        boxes.append((width, height))

    return errors, class_counts, boxes, len(lines)


def verify_dataset(dataset_dir: Path) -> int:
    dataset_dir = dataset_dir.resolve()
    classes = load_yaml_classes(dataset_dir)
    errors = []
    warnings = []
    split_stats = {}
    total_images = 0
    total_labels = 0
    total_objects = 0
    empty_labels = 0
    class_counts = Counter()
    all_boxes = []

    for split in ["train", "val", "test"]:
        image_dir = dataset_dir / "images" / split
        label_dir = dataset_dir / "labels" / split
        if not image_dir.exists():
            errors.append(f"missing directory: {image_dir}")
            continue
        if not label_dir.exists():
            errors.append(f"missing directory: {label_dir}")
            continue

        images = collect_images(image_dir)
        labels = {item.stem: item for item in label_dir.glob("*.txt")}
        missing_labels = sorted(set(images) - set(labels))
        orphan_labels = sorted(set(labels) - set(images))
        if missing_labels:
            errors.append(f"{split}: {len(missing_labels)} images missing labels")
        if orphan_labels:
            errors.append(f"{split}: {len(orphan_labels)} labels missing images")

        split_objects = 0
        for label_path in labels.values():
            label_errors, label_class_counts, boxes, line_count = verify_label_file(label_path, len(classes))
            errors.extend(label_errors)
            class_counts.update(label_class_counts)
            all_boxes.extend(boxes)
            split_objects += len(boxes)
            if line_count == 0:
                empty_labels += 1

        split_stats[split] = {
            "images": len(images),
            "labels": len(labels),
            "objects": split_objects,
        }
        total_images += len(images)
        total_labels += len(labels)
        total_objects += split_objects

    nonzero_counts = [count for count in class_counts.values() if count > 0]
    if nonzero_counts and max(nonzero_counts) / min(nonzero_counts) > 10:
        warnings.append("class distribution is severely imbalanced")

    print("=" * 70)
    print("YOLO dataset verification report")
    print("=" * 70)
    print(f"dataset: {dataset_dir}")
    print(f"classes: {classes}")
    print()
    print("[overall]")
    print(f"  images: {total_images}")
    print(f"  label files: {total_labels}")
    print(f"  objects: {total_objects}")
    print(f"  empty labels: {empty_labels}")
    print(f"  avg objects/image: {total_objects / total_images:.2f}" if total_images else "  avg objects/image: 0")
    print()
    print("[splits]")
    for split, stats in split_stats.items():
        print(f"  {split}: {stats['images']} images, {stats['labels']} labels, {stats['objects']} objects")
    print()
    print("[class distribution]")
    for class_id, name in classes.items():
        count = class_counts[class_id]
        pct = count / total_objects * 100 if total_objects else 0
        print(f"  {class_id}. {name}: {count} ({pct:.2f}%)")

    if all_boxes:
        widths = [box[0] for box in all_boxes]
        heights = [box[1] for box in all_boxes]
        areas = [box[0] * box[1] for box in all_boxes]
        small = sum(1 for area in areas if area < 0.001)
        print()
        print("[bbox]")
        print(f"  avg width: {sum(widths) / len(widths):.6f}")
        print(f"  avg height: {sum(heights) / len(heights):.6f}")
        print(f"  min width: {min(widths):.6f}")
        print(f"  min height: {min(heights):.6f}")
        print(f"  max width: {max(widths):.6f}")
        print(f"  max height: {max(heights):.6f}")
        print(f"  small objects(area < 0.001): {small} ({small / len(areas) * 100:.2f}%)")

    if warnings:
        print()
        print("[warnings]")
        for warning in warnings:
            print(f"  {warning}")

    if errors:
        print()
        print("[errors]")
        for error in errors[:50]:
            print(f"  {error}")
        if len(errors) > 50:
            print(f"  ... {len(errors) - 50} more")
        print("=" * 70)
        print("result: failed")
        return 1

    print("=" * 70)
    print("result: passed")
    return 0


def main():
    dataset_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET
    return verify_dataset(dataset_dir)


if __name__ == "__main__":
    sys.exit(main())
