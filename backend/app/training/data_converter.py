import json
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from app.core.logger import get_logger


logger = get_logger(__name__)


class DataConverter:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    @staticmethod
    def xyxy_to_yolo(xmin: float, ymin: float, xmax: float, ymax: float, img_width: int, img_height: int):
        xmin = max(0.0, min(float(xmin), float(img_width)))
        ymin = max(0.0, min(float(ymin), float(img_height)))
        xmax = max(0.0, min(float(xmax), float(img_width)))
        ymax = max(0.0, min(float(ymax), float(img_height)))

        if xmax <= xmin or ymax <= ymin or img_width <= 0 or img_height <= 0:
            return None

        x_center = (xmin + xmax) / 2.0 / img_width
        y_center = (ymin + ymax) / 2.0 / img_height
        width = (xmax - xmin) / img_width
        height = (ymax - ymin) / img_height
        return x_center, y_center, width, height

    @classmethod
    def voc_xml_to_yolo_lines(cls, xml_path: str | os.PathLike, class_mapping: dict[str, int]) -> list[str]:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        size = root.find("size")
        if size is None:
            raise ValueError(f"{xml_path} missing size")

        img_width = int(float(size.findtext("width", "0")))
        img_height = int(float(size.findtext("height", "0")))
        if img_width <= 0 or img_height <= 0:
            raise ValueError(f"{xml_path} invalid image size")

        yolo_lines = []
        for obj in root.findall("object"):
            class_name = (obj.findtext("name") or "").strip()
            if class_name not in class_mapping:
                logger.warning("Skip unknown class '%s' in %s", class_name, xml_path)
                continue

            bbox = obj.find("bndbox")
            if bbox is None:
                continue

            converted = cls.xyxy_to_yolo(
                float(bbox.findtext("xmin", "0")),
                float(bbox.findtext("ymin", "0")),
                float(bbox.findtext("xmax", "0")),
                float(bbox.findtext("ymax", "0")),
                img_width,
                img_height,
            )
            if converted is None:
                logger.warning("Skip invalid bbox in %s", xml_path)
                continue

            x_center, y_center, width, height = converted
            yolo_lines.append(
                f"{class_mapping[class_name]} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
            )

        return yolo_lines

    @classmethod
    def voc_to_yolo(
        cls,
        xml_dir: str | os.PathLike,
        output_dir: str | os.PathLike,
        class_mapping: dict[str, int],
        include_ids: set[str] | None = None,
    ) -> dict:
        xml_dir = Path(xml_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stats = {"total": 0, "converted": 0, "skipped": 0, "errors": []}
        xml_files = sorted(xml_dir.glob("*.xml"))

        for xml_file in xml_files:
            if include_ids is not None and xml_file.stem not in include_ids:
                continue

            stats["total"] += 1
            try:
                lines = cls.voc_xml_to_yolo_lines(xml_file, class_mapping)
                (output_dir / f"{xml_file.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
                stats["converted"] += 1
            except Exception as exc:
                logger.error("VOC conversion failed for %s: %s", xml_file.name, exc)
                stats["skipped"] += 1
                stats["errors"].append(xml_file.name)

        return stats

    @classmethod
    def coco_to_yolo(
        cls,
        json_path: str | os.PathLike,
        output_dir: str | os.PathLike,
        class_mapping: dict[str, int] | None = None,
    ) -> dict:
        json_path = Path(json_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        images = {item["id"]: item for item in data.get("images", [])}
        categories = {item["id"]: item["name"] for item in data.get("categories", [])}
        if class_mapping is None:
            class_mapping = {name: idx for idx, name in enumerate(categories.values())}

        grouped = defaultdict(list)
        stats = {"total": len(data.get("annotations", [])), "converted": 0, "skipped": 0, "errors": []}

        for ann in data.get("annotations", []):
            image = images.get(ann.get("image_id"))
            class_name = categories.get(ann.get("category_id"))
            if image is None or class_name not in class_mapping:
                stats["skipped"] += 1
                continue

            x, y, w, h = ann.get("bbox", [0, 0, 0, 0])
            converted = cls.xyxy_to_yolo(x, y, x + w, y + h, int(image["width"]), int(image["height"]))
            if converted is None:
                stats["skipped"] += 1
                continue

            line = f"{class_mapping[class_name]} {converted[0]:.6f} {converted[1]:.6f} {converted[2]:.6f} {converted[3]:.6f}"
            grouped[Path(image["file_name"]).stem].append(line)
            stats["converted"] += 1

        for stem, lines in grouped.items():
            (output_dir / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")

        return stats

    @classmethod
    def labelme_to_yolo(
        cls,
        json_dir: str | os.PathLike,
        output_dir: str | os.PathLike,
        class_mapping: dict[str, int],
    ) -> dict:
        json_dir = Path(json_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stats = {"total": 0, "converted": 0, "skipped": 0, "errors": []}
        for json_file in sorted(json_dir.glob("*.json")):
            stats["total"] += 1
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                img_width = int(data.get("imageWidth", 0))
                img_height = int(data.get("imageHeight", 0))
                lines = []

                for shape in data.get("shapes", []):
                    label = shape.get("label")
                    if label not in class_mapping:
                        continue

                    points = shape.get("points", [])
                    if len(points) < 2:
                        continue

                    xs = [float(point[0]) for point in points]
                    ys = [float(point[1]) for point in points]
                    converted = cls.xyxy_to_yolo(min(xs), min(ys), max(xs), max(ys), img_width, img_height)
                    if converted is None:
                        continue

                    lines.append(
                        f"{class_mapping[label]} {converted[0]:.6f} {converted[1]:.6f} {converted[2]:.6f} {converted[3]:.6f}"
                    )

                (output_dir / f"{json_file.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
                stats["converted"] += 1
            except Exception as exc:
                logger.error("LabelMe conversion failed for %s: %s", json_file.name, exc)
                stats["skipped"] += 1
                stats["errors"].append(json_file.name)

        return stats
