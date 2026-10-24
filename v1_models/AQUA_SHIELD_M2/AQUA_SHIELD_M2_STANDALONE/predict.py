# predict.py  -  Single-tile inference helper
# Loads the trained U-Net weights and runs it on one 512x512 piece ("tile") of an image.
import os
import numpy as np
import torch
from model import UNet

# Pixels with probability >= 0.45 are counted as oil
THRESHOLD = 0.45

def load_model(checkpoint_path, device=None):
    """Load U-Net model from checkpoint."""
    # Use the GPU (CUDA) if the computer has one, otherwise the CPU
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # Build an empty U-Net with the same shape that was used in training
    model = UNet(n_channels=1, n_classes=1, bilinear=True).to(device)
    # Load the learned weights from the .pth checkpoint file.
    # (weights_only=False allows full Python objects in the file - only load files you trust.)
    state = torch.load(checkpoint_path, map_location=device, weights_only=False)
    # Checkpoints are saved either as {"model_state_dict": weights, ...} or as the weights alone
    if isinstance(state, dict) and 'model_state_dict' in state:
        model.load_state_dict(state['model_state_dict'])
    else:
        model.load_state_dict(state)
    # eval() = inference mode (BatchNorm uses its stored statistics instead of training behaviour)
    model.eval()
    return model, device

def predict_tile(model, tile_np, device, threshold=THRESHOLD):
    """Run inference on a single 512x512 float32 tile (values in [0,1]).
    Returns (prob_map, binary_mask)."""
    # Shape the numpy array (512, 512) into the tensor shape PyTorch expects:
    # (batch=1, channels=1, height=512, width=512)
    tensor = torch.from_numpy(tile_np).unsqueeze(0).unsqueeze(0).float().to(device)
    # no_grad(): we are only predicting, not training, so skip gradient tracking (faster, less memory)
    with torch.no_grad():
        logits = model(tensor)
        # sigmoid squashes raw scores into probabilities between 0 and 1;
        # squeeze() removes the batch/channel dimensions -> back to (512, 512)
        prob = torch.sigmoid(logits).squeeze().cpu().numpy()
    # Binary mask: 255 (white) where prob >= threshold = oil, 0 (black) elsewhere
    mask = (prob >= threshold).astype(np.uint8) * 255
    return prob, mask
