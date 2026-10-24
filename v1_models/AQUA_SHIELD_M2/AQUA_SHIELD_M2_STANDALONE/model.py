# model.py
# ---------------------------------------------------------------------------
# U-Net neural network used to find oil in SAR satellite images (module M2).
#
# A U-Net is an image-segmentation network: input = image, output = an image of the
# same size where each pixel gets a score "how likely is this pixel oil?".
# It has a "U" shape:
#
#   input 1x512x512 ─ inc(64) ──────────────────────────────── up4(64) ─ outc ─> 1x512x512 score map
#                       └ down1(128) ───────────────────── up3(64)
#                            └ down2(256) ──────────── up2(128)
#                                 └ down3(512) ── up1(256)
#                                      └ down4(512)   (bottom of the "U")
#
#   - Left side (encoder): shrinks the image (MaxPool) while learning more features
#     (channels 64 -> 512) = understands WHAT is in the image.
#   - Right side (decoder): enlarges back to full size = figures out WHERE it is.
#   - Horizontal lines = "skip connections": copy fine details from the left side to the
#     right side so the output outline stays sharp.
# ---------------------------------------------------------------------------
import torch
import torch.nn as nn

class DoubleConv(nn.Module):
    """(conv => BN => ReLU) * 2"""
    # The basic building block, used at every level of the U:
    #   Conv2d 3x3   - slides a small 3x3 filter over the image to detect patterns
    #   BatchNorm2d  - keeps values in a stable range, makes training faster/stabler
    #   ReLU         - activation: keeps positive values, sets negatives to 0 (adds non-linearity)
    # padding=1 keeps the width/height the same after each convolution.
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
    def forward(self, x):
        return self.double_conv(x)

class Down(nn.Module):
    """Downscaling with maxpool then double conv"""
    # MaxPool2d(2) halves width and height (keeps the strongest value in each 2x2 block),
    # then DoubleConv learns features at this smaller scale.
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            DoubleConv(in_channels, out_channels)
        )
    def forward(self, x):
        return self.maxpool_conv(x)

class Up(nn.Module):
    """Upscaling then double conv. Uses either bilinear upsample or transposed conv"""
    # Doubles width and height again, then joins it with the matching encoder output
    # (skip connection) before a DoubleConv.
    def __init__(self, in_channels, out_channels, bilinear=True):
        super().__init__()
        if bilinear:
            # Simple smooth resize (no learned weights)
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels)
        else:
            # Learned upsampling ("transposed convolution")
            self.up = nn.ConvTranspose2d(in_channels // 2, in_channels // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels)
    def forward(self, x1, x2):
        # x1 = output from the level below (smaller), x2 = skip connection from the encoder
        x1 = self.up(x1)
        # Pad if needed (should not be required for 512 -> powers of 2)
        diffY = x2.size(2) - x1.size(2)
        diffX = x2.size(3) - x1.size(3)
        if diffY != 0 or diffX != 0:
            x1 = nn.functional.pad(x1, [diffX // 2, diffX - diffX // 2,
                                         diffY // 2, diffY - diffY // 2])
        # Stack both along the channel dimension (dim=1) -> combine "what" and "where"
        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)

class OutConv(nn.Module):
    # Final 1x1 convolution: turns 64 feature channels into 1 score per pixel
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)
    def forward(self, x):
        return self.conv(x)

class UNet(nn.Module):
    # n_channels=1: SAR images are single-band (grayscale)
    # n_classes=1 : one output = "oil" score (background is just a low score)
    def __init__(self, n_channels=1, n_classes=1, bilinear=True):
        super().__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        # Encoder (left side of the U)
        self.inc = DoubleConv(n_channels, 64)
        self.down1 = Down(64, 128)
        self.down2 = Down(128, 256)
        self.down3 = Down(256, 512)
        factor = 2 if bilinear else 1
        self.down4 = Down(512, 1024 // factor)
        # Decoder (right side of the U)
        self.up1 = Up(1024, 512 // factor, bilinear)
        self.up2 = Up(512, 256 // factor, bilinear)
        self.up3 = Up(256, 128 // factor, bilinear)
        self.up4 = Up(128, 64, bilinear)
        self.outc = OutConv(64, n_classes)

    def forward(self, x):
        # Going down: each step halves the size  (512 -> 256 -> 128 -> 64 -> 32)
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        # Going up: each step doubles the size and re-uses the matching encoder output
        x = self.up1(x5, x4)
        x = self.up2(x, x3)
        x = self.up3(x, x2)
        x = self.up4(x, x1)
        # "logits" = raw scores (any number). sigmoid() later turns them into 0..1 probabilities.
        logits = self.outc(x)
        return logits
