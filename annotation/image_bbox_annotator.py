"""Bounding box annotation export: YOLO, COCO, Pascal VOC."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List

from PIL import Image


ANNOTATIONS_DIR = Path("storage/annotations")


def _ensure_dir() -> None:
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)


def _classes_index(boxes: List[dict]) -> List[str]:
    seen: list[str] = []
    for b in boxes:
        c = str(b.get("class", "object"))
        if c not in seen:
            seen.append(c)
    return seen


def _save_yolo(image_path: Path, boxes: List[dict], width: int, height: int) -> Path:
    classes = _classes_index(boxes)
    out_txt = ANNOTATIONS_DIR / f"{image_path.stem}.txt"
    lines = []
    for b in boxes:
        cls_id = classes.index(str(b.get("class", "object")))
        x1, y1, x2, y2 = (
            float(b["x1"]),
            float(b["y1"]),
            float(b["x2"]),
            float(b["y2"]),
        )
        x_c = ((x1 + x2) / 2) / max(width, 1)
        y_c = ((y1 + y2) / 2) / max(height, 1)
        w = abs(x2 - x1) / max(width, 1)
        h = abs(y2 - y1) / max(height, 1)
        lines.append(f"{cls_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}")
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    classes_txt = ANNOTATIONS_DIR / "classes.txt"
    classes_txt.write_text("\n".join(classes) + "\n", encoding="utf-8")
    return out_txt


def _save_coco(image_path: Path, boxes: List[dict], width: int, height: int) -> Path:
    classes = _classes_index(boxes)
    coco = {
        "info": {
            "description": "AutoPrompt Annotator export",
            "date_created": datetime.utcnow().isoformat(),
        },
        "images": [
            {
                "id": 1,
                "file_name": image_path.name,
                "width": width,
                "height": height,
            }
        ],
        "categories": [
            {"id": i + 1, "name": c, "supercategory": "object"}
            for i, c in enumerate(classes)
        ],
        "annotations": [],
    }
    for i, b in enumerate(boxes, start=1):
        x1, y1, x2, y2 = (
            float(b["x1"]),
            float(b["y1"]),
            float(b["x2"]),
            float(b["y2"]),
        )
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        cls_id = classes.index(str(b.get("class", "object"))) + 1
        coco["annotations"].append(
            {
                "id": i,
                "image_id": 1,
                "category_id": cls_id,
                "bbox": [min(x1, x2), min(y1, y2), w, h],
                "area": w * h,
                "iscrowd": 0,
            }
        )
    out = ANNOTATIONS_DIR / f"{image_path.stem}.json"
    out.write_text(json.dumps(coco, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _save_voc(image_path: Path, boxes: List[dict], width: int, height: int) -> Path:
    annotation = ET.Element("annotation")
    ET.SubElement(annotation, "folder").text = "uploads"
    ET.SubElement(annotation, "filename").text = image_path.name
    ET.SubElement(annotation, "path").text = str(image_path)

    size = ET.SubElement(annotation, "size")
    ET.SubElement(size, "width").text = str(width)
    ET.SubElement(size, "height").text = str(height)
    ET.SubElement(size, "depth").text = "3"

    ET.SubElement(annotation, "segmented").text = "0"

    for b in boxes:
        obj = ET.SubElement(annotation, "object")
        ET.SubElement(obj, "name").text = str(b.get("class", "object"))
        ET.SubElement(obj, "pose").text = "Unspecified"
        ET.SubElement(obj, "truncated").text = "0"
        ET.SubElement(obj, "difficult").text = "0"
        bb = ET.SubElement(obj, "bndbox")
        x1, y1, x2, y2 = (
            int(float(b["x1"])),
            int(float(b["y1"])),
            int(float(b["x2"])),
            int(float(b["y2"])),
        )
        ET.SubElement(bb, "xmin").text = str(min(x1, x2))
        ET.SubElement(bb, "ymin").text = str(min(y1, y2))
        ET.SubElement(bb, "xmax").text = str(max(x1, x2))
        ET.SubElement(bb, "ymax").text = str(max(y1, y2))

    tree = ET.ElementTree(annotation)
    out = ANNOTATIONS_DIR / f"{image_path.stem}.xml"
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out


def save_bbox_annotation(
    image_path: str, boxes: List[dict], format: str
) -> str:
    """Persist bbox annotations. `format` is one of "yolo", "coco", "voc"."""
    _ensure_dir()
    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(image_path)

    with Image.open(img_path) as img:
        width, height = img.size

    fmt = (format or "").lower()
    if fmt == "yolo":
        return str(_save_yolo(img_path, boxes, width, height))
    if fmt == "coco":
        return str(_save_coco(img_path, boxes, width, height))
    if fmt in ("voc", "pascal_voc", "pascalvoc"):
        return str(_save_voc(img_path, boxes, width, height))
    raise ValueError(f"Неизвестный формат: {format}")
