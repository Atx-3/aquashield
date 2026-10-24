# utils.py  -  Tiling, normalization, stitching, and visualisation helpers
# The U-Net works on fixed 512x512 pieces, but satellite images can be any size.
# So we: normalize -> cut into 512x512 tiles -> predict each tile -> stitch results back.
import numpy as np
from PIL import Image

TILE_SIZE = 512

def normalize_image(arr):
    """Min-max normalize a float32 array to [0, 1]."""
    # Remove negative values, then divide by the brightest pixel so all values are 0..1
    # (the model was trained on images scaled this way)
    arr = np.clip(arr, a_min=0, a_max=None).astype(np.float32)
    max_val = arr.max()
    if max_val > 0:
        arr /= max_val
    return arr

def split_to_tiles(image, tile_size=TILE_SIZE):
    """Split a 2D array into non-overlapping tiles.
    Returns list of (row_idx, col_idx, tile_array)."""
    h, w = image.shape
    tiles = []
    # Walk over the image in steps of 512 pixels, top-to-bottom and left-to-right
    for i in range(0, h, tile_size):
        for j in range(0, w, tile_size):
            tile = image[i:i+tile_size, j:j+tile_size]
            # Tiles at the right/bottom edge can be smaller -> pad them with zeros to 512x512
            if tile.shape != (tile_size, tile_size):
                padded = np.zeros((tile_size, tile_size), dtype=tile.dtype)
                padded[:tile.shape[0], :tile.shape[1]] = tile
                tile = padded
            # Store the tile with its grid position (row number, column number)
            tiles.append((i // tile_size, j // tile_size, tile))
    return tiles

def stitch_tiles(pred_tiles, full_shape, tile_size=TILE_SIZE):
    """Reconstruct full mask and probability map from per-tile predictions.
    pred_tiles: list of (row_idx, col_idx, mask_tile, prob_tile)"""
    h, w = full_shape
    # Empty full-size canvases
    mask = np.zeros((h, w), dtype=np.uint8)
    prob = np.zeros((h, w), dtype=np.float32)
    for row_idx, col_idx, tile_mask, tile_prob in pred_tiles:
        # Top-left pixel of this tile in the full image
        i = row_idx * tile_size
        j = col_idx * tile_size
        # Cut off the zero padding added for edge tiles
        th = min(tile_size, h - i)
        tw = min(tile_size, w - j)
        mask[i:i+th, j:j+tw] = tile_mask[:th, :tw]
        prob[i:i+th, j:j+tw] = tile_prob[:th, :tw]
    return mask, prob

def save_png(array, path):
    """Save a 2D array as an 8-bit PNG."""
    # Convert 0..1 floats to 0..255 integers if needed
    if array.dtype != np.uint8:
        arr = (np.clip(array, 0, 1) * 255).astype(np.uint8)
    else:
        arr = array
    Image.fromarray(arr).save(str(path))

def overlay_mask(sar_img, mask):
    """Create an overlay image: mask=255 shown in red over SAR grayscale."""
    sar_uint8 = (np.clip(sar_img, 0, 1) * 255).astype(np.uint8)
    # Grayscale -> RGB by copying the single channel three times
    sar_rgb = np.stack([sar_uint8]*3, axis=2)
    overlay = sar_rgb.copy()
    # Paint every oil pixel pure red
    overlay[mask == 255] = [255, 0, 0]
    return Image.fromarray(overlay)
