# AQUA SHIELD M2 Standalone Inference Package

Portable, inference-only package for the **AQUA SHIELD M2** satellite oil-spill
segmentation model (U-Net, Epoch 27, Val Dice ~ 0.0794).

## Quick Start

```bash
pip install -r requirements.txt
python run_inference.py --tiff path/to/scene.tif --outdir outputs
```

## Outputs

| File | Description |
|------|-------------|
| `<name>_sar.png` | Original SAR image (8-bit) |
| `<name>_mask.png` | Binary oil mask (0 / 255) |
| `<name>_overlay.png` | SAR with oil mask overlaid in red |
| `<name>_coverage.txt` | Oil-covered pixel percentage |
| `<name>_prob.npy` | Raw probability map (float32) |

## Model Details

- **Architecture**: Standard U-Net, BatchNorm, bilinear upsampling
- **Training loss**: Weighted BCE (pos_weight=12) + Focal Soft-Dice (gamma=2)
- **Best checkpoint**: Epoch 27, Val Dice = 0.0794
- **Threshold**: 0.45 (optimal from validation sweep)
- **Input**: Single-band SAR GeoTIFF (dimensions must be multiple of 512)

## Files

| File | Purpose |
|------|---------|
| `run_inference.py` | CLI entry point |
| `predict.py` | Single-tile inference |
| `model.py` | U-Net architecture |
| `utils.py` | Tiling, normalization, stitching |
| `requirements.txt` | Python dependencies |
| `checkpoints/best_model.pth` | Trained model weights |

## Requirements

- Python 3.9+
- PyTorch >= 2.0
- Pillow >= 9.0
- NumPy >= 1.24

GPU is used automatically if available; otherwise CPU.
