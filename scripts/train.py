"""
Train YOLOv8n on Rock-Paper-Scissors dataset.
Default: 1 epoch for pipeline validation. Use --epochs N for long training.
"""
import argparse
from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_YAML = BASE_DIR / "data.yaml"
MODELS_DIR = BASE_DIR / "models"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=1, help="Number of training epochs")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base model")
    parser.add_argument("--batch", type=int, default=8, help="Batch size")
    parser.add_argument("--device", type=str, default="cuda", help="Device (cuda/cpu)")
    parser.add_argument("--workers", type=int, default=0, help="DataLoader workers (0 for Windows safety)")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Training YOLOv8n on Rock-Paper-Scissors dataset")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch:  {args.batch}")
    print(f"  Device: {args.device}")
    print(f"  Data:   {DATA_YAML}")

    model = YOLO(args.model)

    results = model.train(
        data=str(DATA_YAML),
        epochs=args.epochs,
        imgsz=640,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        amp=False,
        project="runs",
        name="rps_train",
        exist_ok=True,
        verbose=True,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=15.0,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
    )

    # Save best model
    best_src = Path(results.save_dir) / "weights" / "best.pt"
    best_dst = MODELS_DIR / "rps_yolov8n.pt"
    if best_src.exists():
        import shutil
        shutil.copy2(best_src, best_dst)
        print(f"Model saved to: {best_dst}")

    # Validate on test set
    print("\n--- Test Set Validation ---")
    val_results = model.val(data=str(DATA_YAML), split="test", verbose=True)
    print(f"Test mAP@50:    {val_results.box.map50:.4f}")
    print(f"Test mAP@50-95: {val_results.box.map:.4f}")

    print("\nDone!")


if __name__ == "__main__":
    main()
