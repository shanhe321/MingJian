import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_PARENT = PROJECT_ROOT.parent.parent
DEFAULT_SOURCE = REPO_PARENT / "Dataset" / "1" / "VOC_PCB"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "pcb_defect"
sys.path.insert(0, str(PROJECT_ROOT))

CLASS_NAMES = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]
CLASS_MAPPING = {name: idx for idx, name in enumerate(CLASS_NAMES)}


def parse_args():
    parser = argparse.ArgumentParser(description="Convert VOC PCB dataset to YOLO format.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="VOC dataset root with JPEGImages/Annotations/ImageSets.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output YOLO dataset directory.")
    parser.add_argument("--clean", action="store_true", help="Delete output directory before conversion.")
    return parser.parse_args()


def main():
    from app.training.data_converter import DataConverter
    from app.training.dataset_splitter import DatasetSplitter

    args = parse_args()
    source_dir = Path(args.source)
    output_dir = Path(args.output)

    image_dir = source_dir / "JPEGImages"
    xml_dir = source_dir / "Annotations"
    split_dir = source_dir / "ImageSets" / "Main"
    temp_label_dir = output_dir / "_temp_labels"

    if not image_dir.exists() or not xml_dir.exists():
        print(f"[ERROR] Invalid VOC dataset: {source_dir}")
        return 1

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)

    temp_label_dir.mkdir(parents=True, exist_ok=True)

    split_files = {
        "train": split_dir / "train.txt",
        "val": split_dir / "val.txt",
        "test": split_dir / "test.txt",
    }
    split_ids = set()
    for split_file in split_files.values():
        split_ids.update(DatasetSplitter.read_split_file(split_file))

    print("=" * 70)
    print("VOC PCB -> YOLO conversion")
    print("=" * 70)
    print(f"source: {source_dir}")
    print(f"output: {output_dir}")
    print(f"classes: {CLASS_NAMES}")

    convert_stats = DataConverter.voc_to_yolo(
        xml_dir=xml_dir,
        output_dir=temp_label_dir,
        class_mapping=CLASS_MAPPING,
        include_ids=split_ids,
    )
    print(f"converted labels: {convert_stats}")

    organize_stats = DatasetSplitter.organize_from_split_files(
        image_dir=image_dir,
        label_dir=temp_label_dir,
        split_files=split_files,
        output_dir=output_dir,
        class_names=CLASS_NAMES,
    )
    print(f"organized dataset: {organize_stats}")

    shutil.rmtree(temp_label_dir, ignore_errors=True)
    print(f"data.yaml: {output_dir / 'data.yaml'}")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
