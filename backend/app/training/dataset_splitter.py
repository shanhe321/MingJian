from __future__ import annotations

import random
import shutil
from pathlib import Path

from app.core.logger import get_logger

logger = get_logger(__name__)


class DatasetSplitter:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

    @staticmethod
    def read_split_file(split_file: str | Path) -> list[str]:
        return [
            line.strip()
            for line in Path(split_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @classmethod
    def find_image(cls, image_dir: str | Path, image_id: str) -> Path | None:
        image_dir = Path(image_dir)
        for extension in cls.image_exts:
            candidate = image_dir / f"{image_id}{extension}"
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def generate_data_yaml(
        output_dir: str | Path,
        class_names: list[str],
        class_names_cn: list[str] | None = None,
    ) -> str:
        import yaml

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        data_config = {
            "path": f"./{output_path.name}",
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": len(class_names),
            "names": {index: name for index, name in enumerate(class_names)},
        }
        if class_names_cn:
            if len(class_names_cn) != len(class_names):
                raise ValueError("class_names_cn 必须与 class_names 长度一致")
            data_config["names_cn"] = {
                index: name for index, name in enumerate(class_names_cn)
            }
        yaml_path = output_path / "data.yaml"
        with yaml_path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(
                data_config,
                file,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        logger.info("data.yaml 已生成：%s", yaml_path)
        return str(yaml_path)

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
        for split in ("train", "val", "test"):
            (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
        for split, split_file in split_files.items():
            identifiers = cls.read_split_file(split_file)
            split_stats = {"ids": len(identifiers), "images": 0, "labels": 0}
            for image_id in identifiers:
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
        class_names: list[str] | None = None,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
        seed: int = 42,
    ) -> dict:
        if min(train_ratio, val_ratio, test_ratio) < 0:
            raise ValueError("数据集划分比例不能为负数")
        if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-6:
            raise ValueError("train_ratio + val_ratio + test_ratio 必须等于 1")

        image_path = Path(image_dir)
        if not image_path.exists():
            return {
                "train": 0,
                "val": 0,
                "test": 0,
                "missing_labels": [],
                "error": "图像目录不存在",
            }
        subdirectories = {path.name for path in image_path.iterdir() if path.is_dir()}
        if {"train", "val", "test"}.issubset(subdirectories):
            stats = cls._organize_from_split_dirs(image_dir, label_dir, output_dir)
        else:
            images = sorted(
                path
                for path in image_path.iterdir()
                if path.is_file() and path.suffix.lower() in cls.image_exts
            )
            if not images:
                return {
                    "train": 0,
                    "val": 0,
                    "test": 0,
                    "missing_labels": [],
                    "error": "未找到图像文件",
                }
            random.Random(seed).shuffle(images)
            train_end = int(len(images) * train_ratio)
            val_end = train_end + int(len(images) * val_ratio)
            splits = {
                "train": images[:train_end],
                "val": images[train_end:val_end],
                "test": images[val_end:],
            }
            stats = {"train": 0, "val": 0, "test": 0, "missing_labels": []}
            source_labels = Path(label_dir)
            destination = Path(output_dir)
            for split, split_images in splits.items():
                image_output = destination / "images" / split
                label_output = destination / "labels" / split
                image_output.mkdir(parents=True, exist_ok=True)
                label_output.mkdir(parents=True, exist_ok=True)
                for source_image in split_images:
                    shutil.copy2(source_image, image_output / source_image.name)
                    source_label = source_labels / f"{source_image.stem}.txt"
                    destination_label = label_output / f"{source_image.stem}.txt"
                    if source_label.exists():
                        shutil.copy2(source_label, destination_label)
                    else:
                        destination_label.touch()
                        stats["missing_labels"].append(source_image.name)
                    stats[split] += 1

        if class_names:
            cls.generate_data_yaml(output_dir, class_names)
        logger.info(
            "数据集整理完成：train=%d, val=%d, test=%d, 缺失标注=%d",
            stats["train"],
            stats["val"],
            stats["test"],
            len(stats["missing_labels"]),
        )
        return stats

    @classmethod
    def _organize_from_split_dirs(
        cls, image_dir: str | Path, label_dir: str | Path, output_dir: str | Path
    ) -> dict:
        stats = {"train": 0, "val": 0, "test": 0, "missing_labels": []}
        for split in ("train", "val", "test"):
            source_images = Path(image_dir) / split
            source_labels = Path(label_dir) / split
            destination_images = Path(output_dir) / "images" / split
            destination_labels = Path(output_dir) / "labels" / split
            destination_images.mkdir(parents=True, exist_ok=True)
            destination_labels.mkdir(parents=True, exist_ok=True)
            if not source_images.exists():
                continue
            for source_image in sorted(source_images.iterdir()):
                if not source_image.is_file() or source_image.suffix.lower() not in cls.image_exts:
                    continue
                shutil.copy2(source_image, destination_images / source_image.name)
                source_label = source_labels / f"{source_image.stem}.txt"
                destination_label = destination_labels / f"{source_image.stem}.txt"
                if source_label.exists():
                    shutil.copy2(source_label, destination_label)
                else:
                    destination_label.touch()
                    stats["missing_labels"].append(source_image.name)
                stats[split] += 1
        return stats
