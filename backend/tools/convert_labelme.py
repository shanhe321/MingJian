import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    parser = argparse.ArgumentParser(description="Convert LabelMe JSON files to YOLO labels.")
    parser.add_argument("json_dir", help="Directory containing LabelMe JSON files.")
    parser.add_argument("output_dir", help="Directory for YOLO txt labels.")
    parser.add_argument("--classes", required=True, help="Comma-separated class names in YOLO order.")
    return parser.parse_args()


def main():
    from app.training.data_converter import DataConverter

    args = parse_args()
    class_names = [item.strip() for item in args.classes.split(",") if item.strip()]
    class_mapping = {name: idx for idx, name in enumerate(class_names)}
    stats = DataConverter.labelme_to_yolo(Path(args.json_dir), Path(args.output_dir), class_mapping)
    print(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
