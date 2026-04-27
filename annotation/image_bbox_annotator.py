"""Bounding box and polygon annotation export: YOLO, COCO, Pascal VOC.

Polygons are used for instance-segmentation style annotation. They are
exported as YOLO-seg (`class_id x1 y1 x2 y2 ...` normalized) and COCO
(`segmentation` field as a flat list of floats). Pascal VOC does not
have a standard polygon representation, so for VOC we fall back to the
polygon's axis-aligned bounding box.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PIL import Image


DEFAULT_ANNOTATIONS_DIR = Path("storage/annotations")


def _classes_from_shapes(shapes: List[dict]) -> List[str]:
    seen: list[str] = []
    for s in shapes:
        c = str(s.get("class", "object"))
        if c not in seen:
            seen.append(c)
    return seen


def _shape_bbox(shape: dict) -> tuple[float, float, float, float]:
    """Return (x_min, y_min, x_max, y_max) for a bbox or polygon shape."""
    if "points" in shape:
        xs = [float(p[0]) for p in shape["points"]]
        ys = [float(p[1]) for p in shape["points"]]
        return min(xs), min(ys), max(xs), max(ys)
    return (
        float(min(shape["x1"], shape["x2"])),
        float(min(shape["y1"], shape["y2"])),
        float(max(shape["x1"], shape["x2"])),
        float(max(shape["y1"], shape["y2"])),
    )


# ---------- YOLO ----------

def _save_yolo(
    image_path: Path,
    shapes: List[dict],
    width: int,
    height: int,
    out_dir: Path,
) -> Path:
    classes = _classes_from_shapes(shapes)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_txt = out_dir / f"{image_path.stem}.txt"
    lines: list[str] = []
    for s in shapes:
        cls_id = classes.index(str(s.get("class", "object")))
        if "points" in s and s["points"]:
            # YOLO segmentation: class_id x1 y1 x2 y2 ... (normalized 0..1)
            coords = []
            for x, y in s["points"]:
                coords.append(f"{float(x) / max(width, 1):.6f}")
                coords.append(f"{float(y) / max(height, 1):.6f}")
            lines.append(f"{cls_id} " + " ".join(coords))
        else:
            x1, y1, x2, y2 = _shape_bbox(s)
            x_c = ((x1 + x2) / 2) / max(width, 1)
            y_c = ((y1 + y2) / 2) / max(height, 1)
            w = (x2 - x1) / max(width, 1)
            h = (y2 - y1) / max(height, 1)
            lines.append(f"{cls_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}")
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "classes.txt").write_text("\n".join(classes) + "\n", encoding="utf-8")
    return out_txt


# ---------- COCO ----------

def _save_coco(
    image_path: Path,
    shapes: List[dict],
    width: int,
    height: int,
    out_dir: Path,
) -> Path:
    classes = _classes_from_shapes(shapes)
    coco = {
        "info": {
            "description": "AutoPrompt Annotator export",
            "date_created": datetime.utcnow().isoformat(),
        },
        "images": [
            {"id": 1, "file_name": image_path.name, "width": width, "height": height}
        ],
        "categories": [
            {"id": i + 1, "name": c, "supercategory": "object"}
            for i, c in enumerate(classes)
        ],
        "annotations": [],
    }
    for i, s in enumerate(shapes, start=1):
        cls_id = classes.index(str(s.get("class", "object"))) + 1
        x1, y1, x2, y2 = _shape_bbox(s)
        w = x2 - x1
        h = y2 - y1
        ann = {
            "id": i,
            "image_id": 1,
            "category_id": cls_id,
            "bbox": [x1, y1, w, h],
            "area": float(w * h),
            "iscrowd": 0,
        }
        if "points" in s and s["points"]:
            flat: list[float] = []
            for x, y in s["points"]:
                flat.extend([float(x), float(y)])
            ann["segmentation"] = [flat]
            # Shoelace area for the polygon
            pts = s["points"]
            n = len(pts)
            poly_area = 0.0
            for k in range(n):
                x_i, y_i = float(pts[k][0]), float(pts[k][1])
                x_j, y_j = float(pts[(k + 1) % n][0]), float(pts[(k + 1) % n][1])
                poly_area += (x_i * y_j) - (x_j * y_i)
            ann["area"] = abs(poly_area) / 2.0
        coco["annotations"].append(ann)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{image_path.stem}.json"
    out.write_text(json.dumps(coco, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ---------- Pascal VOC ----------

def _save_voc(
    image_path: Path,
    shapes: List[dict],
    width: int,
    height: int,
    out_dir: Path,
) -> Path:
    annotation = ET.Element("annotation")
    ET.SubElement(annotation, "folder").text = "uploads"
    ET.SubElement(annotation, "filename").text = image_path.name
    ET.SubElement(annotation, "path").text = str(image_path)

    size = ET.SubElement(annotation, "size")
    ET.SubElement(size, "width").text = str(width)
    ET.SubElement(size, "height").text = str(height)
    ET.SubElement(size, "depth").text = "3"

    ET.SubElement(annotation, "segmented").text = "1" if any("points" in s for s in shapes) else "0"

    for s in shapes:
        obj = ET.SubElement(annotation, "object")
        ET.SubElement(obj, "name").text = str(s.get("class", "object"))
        ET.SubElement(obj, "pose").text = "Unspecified"
        ET.SubElement(obj, "truncated").text = "0"
        ET.SubElement(obj, "difficult").text = "0"
        x1, y1, x2, y2 = _shape_bbox(s)
        bb = ET.SubElement(obj, "bndbox")
        ET.SubElement(bb, "xmin").text = str(int(x1))
        ET.SubElement(bb, "ymin").text = str(int(y1))
        ET.SubElement(bb, "xmax").text = str(int(x2))
        ET.SubElement(bb, "ymax").text = str(int(y2))
        if "points" in s and s["points"]:
            poly = ET.SubElement(obj, "polygon")
            for k, (x, y) in enumerate(s["points"], start=1):
                ET.SubElement(poly, f"x{k}").text = str(int(float(x)))
                ET.SubElement(poly, f"y{k}").text = str(int(float(y)))

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{image_path.stem}.xml"
    ET.ElementTree(annotation).write(out, encoding="utf-8", xml_declaration=True)
    return out


# ---------- public API ----------

def save_shape_annotation(
    image_path: str,
    shapes: List[dict],
    format: str,
    output_dir: Optional[Path] = None,
) -> str:
    """Save bbox+polygon shapes in the requested format.

    `shapes` items can be either:
        {"class": str, "x1": int, "y1": int, "x2": int, "y2": int}            # bbox
        {"class": str, "points": [[x, y], [x, y], ...]}                       # polygon
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_ANNOTATIONS_DIR
    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(image_path)
    with Image.open(img_path) as img:
        width, height = img.size

    fmt = (format or "").lower()
    if fmt == "yolo":
        return str(_save_yolo(img_path, shapes, width, height, out_dir))
    if fmt == "coco":
        return str(_save_coco(img_path, shapes, width, height, out_dir))
    if fmt in ("voc", "pascal_voc", "pascalvoc"):
        return str(_save_voc(img_path, shapes, width, height, out_dir))
    raise ValueError(f"Неизвестный формат: {format}")


def save_bbox_annotation(
    image_path: str,
    boxes: List[dict],
    format: str,
    output_dir: Optional[Path] = None,
) -> str:
    """Backwards-compatible bbox-only API. Wraps `save_shape_annotation`."""
    return save_shape_annotation(image_path, boxes, format, output_dir)
