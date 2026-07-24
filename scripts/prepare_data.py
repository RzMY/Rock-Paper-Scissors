"""
Convert Roboflow Pascal VOC CSV annotations to YOLO txt format.
Creates train/val/test splits with labels and generates data.yaml.
"""
import csv
import os
import shutil
from pathlib import Path
from collections import defaultdict

import numpy as np
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = BASE_DIR / "datasets"
TRAIN_DIR = DATASETS_DIR / "train"
TEST_DIR = DATASETS_DIR / "test"
VAL_DIR = DATASETS_DIR / "val"

CLASS_MAP = {"Rock": 0, "Paper": 1, "Scissors": 2}
CLASS_NAMES = {0: "Rock", 1: "Paper", 2: "Scissors"}


def parse_csv(csv_path: Path):
    """Parse Roboflow _annotations.csv. Returns dict: filename -> list of (class_id, xmin, ymin, xmax, ymax)."""
    annotations = defaultdict(list)
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = (row.get("filename") or "").strip()
            if not filename:
                continue
            cls_name = (row.get("class") or "").strip()
            if cls_name not in CLASS_MAP:
                continue
            try:
                xmin = float(row["xmin"])
                ymin = float(row["ymin"])
                xmax = float(row["xmax"])
                ymax = float(row["ymax"])
            except (KeyError, ValueError):
                continue
            annotations[filename].append((CLASS_MAP[cls_name], xmin, ymin, xmax, ymax))
    return annotations


def convert_split(annotations: dict, src_images_dir: Path, out_images_dir: Path, labels_dir: Path):
    """
    Convert grouped annotations to YOLO txt format.
    Each txt file has one line per box: class_id cx cy w h (all normalized 0-1).
    Moves images from src_images_dir to out_images_dir.
    Returns: (num_exported, class_counts)
    """
    labels_dir.mkdir(parents=True, exist_ok=True)
    out_images_dir.mkdir(parents=True, exist_ok=True)

    class_counts = defaultdict(int)
    exported = 0

    for filename, boxes in annotations.items():
        src_img = src_images_dir / filename
        if not src_img.exists():
            print(f"  [WARN] Image not found: {filename}")
            continue

        # Write YOLO label file
        label_path = labels_dir / f"{Path(filename).stem}.txt"
        with open(label_path, "w") as f:
            for cls_id, xmin, ymin, xmax, ymax in boxes:
                cx = (xmin + xmax) / 2.0 / 640.0
                cy = (ymin + ymax) / 2.0 / 640.0
                w = (xmax - xmin) / 640.0
                h = (ymax - ymin) / 640.0
                f.write(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
                class_counts[cls_id] += 1

        # Move image to output directory
        dst_img = out_images_dir / filename
        if dst_img != src_img:
            shutil.move(str(src_img), str(dst_img))

        exported += 1

    return exported, dict(class_counts)


def get_primary_label(annotations: dict, filename: str):
    """Return the first class_id for stratified splitting."""
    boxes = annotations.get(filename, [])
    return boxes[0][0] if boxes else 0


def main():
    print("=" * 50)
    print("Rock-Paper-Scissors Data Preparation")
    print("=" * 50)

    # --- Parse annotations ---
    print("\n[1/4] Parsing annotations...")
    train_csv = TRAIN_DIR / "_annotations.csv"
    test_csv = TEST_DIR / "_annotations.csv"

    train_ann = parse_csv(train_csv)
    test_ann = parse_csv(test_csv)

    print(f"  Train: {len(train_ann)} annotated images, "
          f"{sum(len(v) for v in train_ann.values())} total boxes")
    print(f"  Test:  {len(test_ann)} annotated images, "
          f"{sum(len(v) for v in test_ann.values())} total boxes")

    # --- Convert test set ---
    print("\n[2/4] Converting test set...")
    test_count, test_counts = convert_split(
        test_ann,
        src_images_dir=TEST_DIR,
        out_images_dir=TEST_DIR / "images",
        labels_dir=TEST_DIR / "labels",
    )
    print(f"  Exported {test_count} test images with labels")
    for cls_id, count in sorted(test_counts.items()):
        print(f"    {CLASS_NAMES[cls_id]}: {count}")

    # --- Split train into train/val ---
    print("\nSplitting train -> train + val (80/20 stratified)...")
    filenames = list(train_ann.keys())
    labels_for_split = [get_primary_label(train_ann, fn) for fn in filenames]

    train_fns, val_fns = train_test_split(
        filenames, test_size=0.2, stratify=labels_for_split, random_state=42
    )

    train_subset = {fn: train_ann[fn] for fn in train_fns}
    val_subset = {fn: train_ann[fn] for fn in val_fns}

    print(f"  Train: {len(train_subset)} images")
    print(f"  Val:   {len(val_subset)} images")

    # --- Convert train ---
    print("\n[3/4] Converting train set...")
    train_count, train_counts = convert_split(
        train_subset,
        src_images_dir=TRAIN_DIR,
        out_images_dir=TRAIN_DIR / "images",
        labels_dir=TRAIN_DIR / "labels",
    )
    print(f"  Exported {train_count} train images")

    # --- Convert val ---
    print("\n[4/4] Converting val set...")
    val_count, val_counts = convert_split(
        val_subset,
        src_images_dir=TRAIN_DIR,
        out_images_dir=VAL_DIR / "images",
        labels_dir=VAL_DIR / "labels",
    )
    print(f"  Exported {val_count} val images")

    # --- Generate data.yaml ---
    print("\nGenerating data.yaml...")
    data_yaml = BASE_DIR / "data.yaml"
    dataset_path = DATASETS_DIR.resolve().as_posix()

    with open(data_yaml, "w") as f:
        f.write(f"# YOLO dataset config - Rock Paper Scissors\n")
        f.write(f"path: {dataset_path}\n")
        f.write(f"train: train/images\n")
        f.write(f"val: val/images\n")
        f.write(f"test: test/images\n\n")
        f.write(f"nc: 3\n")
        f.write(f"names:\n")
        f.write(f"  0: Rock\n")
        f.write(f"  1: Paper\n")
        f.write(f"  2: Scissors\n")

    print(f"  Written to: {data_yaml}")

    # --- Summary ---
    print("\n" + "=" * 50)
    print("Done! Dataset ready for training.")
    print(f"  data.yaml: {data_yaml}")
    print(f"  Train images: {train_count}")
    print(f"  Val images:   {len(val_subset)}")
    print(f"  Test images:  {test_count}")
    print("=" * 50)


if __name__ == "__main__":
    main()
