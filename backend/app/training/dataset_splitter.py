import random
import shutil
from pathlib import Path


class DatasetSplitter:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    @staticmethod
    def read_split_file(split_file: str | Path) -> list[str]:
        split_file = Path(split_file)
        return [line.strip() for line in split_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    @classmethod
    def find_image(cls, image_dir: str | Path, image_id: str) -> Path | None:
        image_dir = Path(image_dir)
        for ext in cls.image_exts:
            candidate = image_dir / f"{image_id}{ext}"
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def generate_data_yaml(dataset_dir: str | Path, class_names: list[str]) -> Path:
        dataset_dir = Path(dataset_dir)
        lines = [
            f"path: {dataset_dir.resolve().as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            f"nc: {len(class_names)}",
            "names:",
        ]
        lines.extend(f"  {idx}: {name}" for idx, name in enumerate(class_names))

        yaml_path = dataset_dir / "data.yaml"
        yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return yaml_path

    @classmethod
    def organize_from_split_files(
        cls,
        image_dir: str | Path,
        label_dir: str | Path,
        split_files: dict[str, str | Path],
        output_dir: str | Path,
        class_names: list[str],
    ) -> dict:
        image_dir = Path(image_dir)
        label_dir = Path(label_dir)
        output_dir = Path(output_dir)

        stats = {"splits": {}, "missing_images": [], "missing_labels": []}
        for split in ["train", "val", "test"]:
            (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

        for split, split_file in split_files.items():
            ids = cls.read_split_file(split_file)
            split_stats = {"ids": len(ids), "images": 0, "labels": 0}

            for image_id in ids:
                image_path = cls.find_image(image_dir, image_id)
                label_path = label_dir / f"{image_id}.txt"

                if image_path is None:
                    stats["missing_images"].append(image_id)
                    continue
                if not label_path.exists():
                    stats["missing_labels"].append(image_id)
                    continue

                shutil.copy2(image_path, output_dir / "images" / split / image_path.name)
                shutil.copy2(label_path, output_dir / "labels" / split / label_path.name)
                split_stats["images"] += 1
                split_stats["labels"] += 1

            stats["splits"][split] = split_stats

        cls.generate_data_yaml(output_dir, class_names)
        return stats

    @classmethod
    def organize_dataset(
        cls,
        image_dir: str | Path,
        label_dir: str | Path,
        output_dir: str | Path,
        class_names: list[str],
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        seed: int = 42,
    ) -> dict:
        image_dir = Path(image_dir)
        label_dir = Path(label_dir)
        output_dir = Path(output_dir)

        stems = sorted({path.stem for path in image_dir.iterdir() if path.suffix.lower() in cls.image_exts})
        random.Random(seed).shuffle(stems)

        train_end = int(len(stems) * train_ratio)
        val_end = train_end + int(len(stems) * val_ratio)
        splits = {
            "train": stems[:train_end],
            "val": stems[train_end:val_end],
            "test": stems[val_end:],
        }

        temp_split_dir = output_dir / "_splits"
        temp_split_dir.mkdir(parents=True, exist_ok=True)
        split_files = {}
        for split, ids in splits.items():
            split_file = temp_split_dir / f"{split}.txt"
            split_file.write_text("\n".join(ids), encoding="utf-8")
            split_files[split] = split_file

        stats = cls.organize_from_split_files(image_dir, label_dir, split_files, output_dir, class_names)
        shutil.rmtree(temp_split_dir, ignore_errors=True)
        return stats
