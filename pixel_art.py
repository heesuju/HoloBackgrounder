import os
from PIL import Image

def recommend_pixel_size(img):
    """
    Recommends an optimal pixel art grid resolution (max dimension)
    based on the input image's size and non-transparent content.
    Returns an integer: e.g. 16, 32, 48, 64, 96, 128, 192, 256.
    """
    if isinstance(img, str):
        img = Image.open(img)

    w, h = img.size
    max_dim = max(w, h)

    # If image has an alpha channel, check the non-transparent content bounding box
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        try:
            alpha = img.convert('RGBA').split()[-1]
            bbox = alpha.getbbox()
            if bbox:
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]
                max_dim = max(bw, bh)
        except Exception:
            pass

    if max_dim <= 48:
        return 16
    elif max_dim <= 96:
        return 32
    elif max_dim <= 200:
        return 48
    elif max_dim <= 600:
        return 64
    elif max_dim <= 1200:
        return 96
    elif max_dim <= 2400:
        return 128
    else:
        return 192

def process_pixel_art(
    img,
    target_pixel_size=64,
    num_colors=16,
    dither=False,
    crisp_alpha=True,
    output_scale="original"
):
    """
    Converts an image into quantized pixel art.
    
    Parameters:
    - img: PIL Image or path to image
    - target_pixel_size: integer target max dimension (e.g. 16, 32, 64, 128, 256),
      or None/0/'original' for original resolution.
    - num_colors: integer palette color count (e.g. 8, 16, 32, 64),
      or None/0/'original' to keep all colors.
    - dither: bool, whether to apply Floyd-Steinberg dithering.
    - crisp_alpha: bool, threshold alpha to 0 or 255 for clean retro sprite silhouettes.
    - output_scale: 'original', '1x', or integer multiplier (e.g. 2, 4, 8).
    
    Returns:
    - (result_img, (pixel_w, pixel_h))
    """
    if isinstance(img, str):
        img = Image.open(img)

    orig_w, orig_h = img.size

    has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
    if has_alpha:
        img = img.convert('RGBA')
    else:
        img = img.convert('RGB')

    # 1. Determine low-res pixel grid size
    is_orig_size = (
        target_pixel_size is None or
        target_pixel_size == 0 or
        str(target_pixel_size).lower() == 'original' or
        (isinstance(target_pixel_size, int) and target_pixel_size >= max(orig_w, orig_h))
    )

    if is_orig_size:
        tw, th = orig_w, orig_h
        small = img.copy()
    else:
        pts = int(target_pixel_size)
        if orig_w >= orig_h:
            tw = max(1, pts)
            th = max(1, int(round(orig_h * pts / orig_w)))
        else:
            th = max(1, pts)
            tw = max(1, int(round(orig_w * pts / orig_h)))

        # BOX resampling averages pixel blocks cleanly when downscaling heavily
        resample = Image.Resampling.BOX if (orig_w / tw >= 1.5 or orig_h / th >= 1.5) else Image.Resampling.BILINEAR
        small = img.resize((tw, th), resample)

    # 2. Color Quantization & Transparency Handling
    dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE

    is_orig_colors = (
        num_colors is None or
        num_colors == 0 or
        str(num_colors).lower() == 'original' or
        (isinstance(num_colors, int) and num_colors >= 256 and not dither)
    )

    if has_alpha:
        r, g, b, a = small.split()
        if crisp_alpha:
            a = a.point(lambda p: 255 if p >= 128 else 0)

        if not is_orig_colors:
            colors_count = max(2, min(256, int(num_colors)))
            rgb = Image.merge('RGB', (r, g, b))
            q_rgb = rgb.quantize(colors=colors_count, dither=dither_mode).convert('RGB')
            processed_small = Image.merge('RGBA', (*q_rgb.split(), a))
        else:
            processed_small = Image.merge('RGBA', (r, g, b, a))
    else:
        if not is_orig_colors:
            colors_count = max(2, min(256, int(num_colors)))
            processed_small = small.quantize(colors=colors_count, dither=dither_mode).convert('RGB')
        else:
            processed_small = small

    # 3. Output Scaling
    if output_scale == "original":
        result = processed_small.resize((orig_w, orig_h), Image.Resampling.NEAREST)
    elif output_scale == "1x" or output_scale == 1:
        result = processed_small
    elif isinstance(output_scale, int) and output_scale > 1:
        result = processed_small.resize((tw * output_scale, th * output_scale), Image.Resampling.NEAREST)
    else:
        result = processed_small.resize((orig_w, orig_h), Image.Resampling.NEAREST)

    return result, (tw, th)
