import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XML_DIR = PROJECT_ROOT.parent.parent / "Dataset" / "1" / "VOC_PCB" / "Annotations"


def fix_xml_file(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find("size")
    if size is None:
        return 0, 0
    img_width = int(float(size.findtext("width", "0")))
    img_height = int(float(size.findtext("height", "0")))
    fixed = 0
    deleted = 0
    to_delete = []
    for obj in root.findall("object"):
        bbox = obj.find("bndbox")
        if bbox is None:
            continue
        values = {
            "xmin": float(bbox.findtext("xmin", "0")),
            "ymin": float(bbox.findtext("ymin", "0")),
            "xmax": float(bbox.findtext("xmax", "0")),
            "ymax": float(bbox.findtext("ymax", "0")),
        }
        clipped = {
            "xmin": max(0.0, min(values["xmin"], img_width)),
            "ymin": max(0.0, min(values["ymin"], img_height)),
            "xmax": max(0.0, min(values["xmax"], img_width)),
            "ymax": max(0.0, min(values["ymax"], img_height)),
        }
        if clipped["xmax"] <= clipped["xmin"] or clipped["ymax"] <= clipped["ymin"]:
            to_delete.append(obj)
            deleted += 1
            continue
        if clipped != values:
            fixed += 1
            for key, value in clipped.items():
                bbox.find(key).text = str(int(value))
    for obj in to_delete:
        root.remove(obj)
    if fixed or deleted:
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return fixed, deleted


def main():
    xml_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XML_DIR
    total_fixed = 0
    total_deleted = 0
    for xml_path in xml_dir.glob("*.xml"):
        fixed, deleted = fix_xml_file(xml_path)
        total_fixed += fixed
        total_deleted += deleted
    print({"fixed": total_fixed, "deleted": total_deleted})
    return 0


if __name__ == "__main__":
    sys.exit(main())
