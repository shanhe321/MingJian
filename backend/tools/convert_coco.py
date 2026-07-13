import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    parser = argparse.ArgumentParser(description="Convert COCO JSON annotations to YOLO labels.")
    parser.add_argument("json_path", help="Path to COCO annotation JSON.")
    parser.add_argument("output_dir", help="Directory for YOLO txt labels.")
    return parser.parse_args()


def main():
    from app.training.data_converter import DataConverter

    args = parse_args()
    stats = DataConverter.coco_to_yolo(Path(args.json_path), Path(args.output_dir))
    print(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
