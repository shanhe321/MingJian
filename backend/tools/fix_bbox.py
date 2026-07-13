import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "pcb_defect"


def fix_label_file(label_path: Path):
    fixed = 0
    deleted = 0
    new_lines = []
    for raw_line in label_path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.strip().split()
        if len(parts) != 5:
            deleted += 1
            continue
        try:
            class_id = int(parts[0])
            values = [float(value) for value in parts[1:]]
        except ValueError:
            deleted += 1
            continue
        clipped = [max(0.0, min(1.0, value)) for value in values]
        if clipped != values:
            fixed += 1
        if clipped[2] <= 0 or clipped[3] <= 0:
            deleted += 1
            continue
        new_lines.append(f"{class_id} {clipped[0]:.6f} {clipped[1]:.6f} {clipped[2]:.6f} {clipped[3]:.6f}")
    label_path.write_text("\n".join(new_lines), encoding="utf-8")
    return fixed, deleted


def main():
    dataset_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET
    total_fixed = 0
    total_deleted = 0
    for label_path in (dataset_dir / "labels").glob("*/*.txt"):
        fixed, deleted = fix_label_file(label_path)
        total_fixed += fixed
        total_deleted += deleted
    print({"fixed": total_fixed, "deleted": total_deleted})
    return 0


if __name__ == "__main__":
    sys.exit(main())
