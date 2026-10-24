#!/usr/bin/env python
"""run_inference.py

Command-line entry point.  Reads a single-band SAR GeoTIFF, tiles it,
runs the U-Net model, stitches the results, and writes outputs.

Usage:
    python run_inference.py --tiff path/to/scene.tif --outdir outputs

This is the stand-alone version of the detector (used for testing the model on its own,
outside the web app). It writes 5 files to the output folder:
    <name>_sar.png       normalized input image
    <name>_mask.png      white = oil, black = not oil
    <name>_overlay.png   input image with oil painted red
    <name>_coverage.txt  % of the image classified as oil
    <name>_prob.npy      raw probability map (numpy array)
"""
import argparse
import os
import numpy as np
from pathlib import Path
from PIL import Image

from predict import load_model, predict_tile, THRESHOLD
from utils import normalize_image, split_to_tiles, stitch_tiles, save_png, overlay_mask

TILE_SIZE = 512
DEFAULT_CHECKPOINT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "checkpoints", "best_model.pth")

def read_tiff(tiff_path):
    """Read a single-band GeoTIFF and return a float32 array normalized to [0,1]."""
    img = Image.open(str(tiff_path))
    # "F" = 32-bit float grayscale, "L" = 8-bit grayscale; convert anything else to float
    if img.mode not in ("F", "L"):
        img = img.convert("F")
    arr = np.array(img, dtype=np.float32)
    return normalize_image(arr)

def main():
    # Read command-line options (--tiff, --outdir, --checkpoint, --threshold)
    parser = argparse.ArgumentParser(description="AQUA SHIELD M2 Oil-Spill Inference")
    parser.add_argument("--tiff", required=True,
                        help="Path to input GeoTIFF (single-band SAR).")
    parser.add_argument("--outdir", default="outputs",
                        help="Directory to write outputs.")
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT,
                        help="Path to .pth checkpoint.")
    parser.add_argument("--threshold", type=float, default=THRESHOLD,
                        help="Binary threshold (default 0.45).")
    args = parser.parse_args()

    tiff_path = Path(args.tiff)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load model
    if not os.path.isfile(args.checkpoint):
        raise FileNotFoundError(f"Checkpoint not found: {args.checkpoint}")
    model, device = load_model(args.checkpoint)
    print(f"Model loaded on {device}.")

    # Read input
    sar = read_tiff(tiff_path)
    h, w = sar.shape
    print(f"Input image: {h} x {w}")

    # Tile, predict, stitch
    tiles = split_to_tiles(sar, TILE_SIZE)
    pred_tiles = []
    for row_idx, col_idx, tile in tiles:
        prob, mask = predict_tile(model, tile, device, threshold=args.threshold)
        pred_tiles.append((row_idx, col_idx, mask, prob))

    full_mask, full_prob = stitch_tiles(pred_tiles, (h, w), TILE_SIZE)

    # Coverage  (percentage of all pixels that were classified as oil)
    oil_pixels = int((full_mask == 255).sum())
    total_pixels = full_mask.size
    coverage = oil_pixels / total_pixels * 100.0

    base_name = tiff_path.stem

    # Save outputs
    save_png(sar, out_dir / f"{base_name}_sar.png")
    save_png(full_mask, out_dir / f"{base_name}_mask.png")
    overlay_img = overlay_mask(sar, full_mask)
    overlay_img.save(str(out_dir / f"{base_name}_overlay.png"))
    with open(out_dir / f"{base_name}_coverage.txt", "w") as cf:
        cf.write(f"Oil coverage: {coverage:.4f}%\n")
        cf.write(f"Oil pixels: {oil_pixels}\n")
        cf.write(f"Total pixels: {total_pixels}\n")
    np.save(str(out_dir / f"{base_name}_prob.npy"), full_prob)

    print(f"\nInference complete.  Oil coverage: {coverage:.4f}%")
    print(f"Outputs saved to: {out_dir.resolve()}")
    for p in sorted(out_dir.iterdir()):
        print(f"  - {p.name}")

if __name__ == "__main__":
    main()
