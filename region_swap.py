from PIL import Image, ImageOps

from image_resizer import RESAMPLE_FILTERS, normalize_mode

FIT_MODES = ("cover", "stretch", "contain")
_META_KEYS = ("icc_profile", "dpi")


def load_image(path):
    """Open an image with EXIF orientation applied and a PNG-friendly mode, so
    the coordinates the user sees in the preview match the saved pixels."""
    with Image.open(path) as img:
        img.load()
        info = {k: img.info[k] for k in _META_KEYS if k in img.info}
        out = normalize_mode(ImageOps.exif_transpose(img))
    out.info.update(info)
    return out


def clamp_region(img_size, x, y, size):
    """Clamp a square region so it lies fully inside an image of img_size."""
    w, h = img_size
    size = max(1, min(int(size), w, h))
    x = max(0, min(int(x), w - size))
    y = max(0, min(int(y), h - size))
    return x, y, size


def extract_region(img, x, y, size):
    """Return the size x size square at (x, y), pixel-for-pixel."""
    x, y, size = clamp_region(img.size, x, y, size)
    out = img.crop((x, y, x + size, y + size))
    out.info.update({k: img.info[k] for k in _META_KEYS if k in img.info})
    return out


def fit_square(img, size, fit="cover", resample="lanczos"):
    """Scale img to a size x size square.
    cover: fill the square, cropping the overflow (centered)
    stretch: ignore aspect ratio
    contain: fit inside the square, padding with transparency"""
    method = RESAMPLE_FILTERS[resample]
    img = normalize_mode(ImageOps.exif_transpose(img))
    target = (size, size)

    if fit == "stretch" or img.width == img.height:
        return img.copy() if img.size == target else img.resize(target, method)
    if fit == "cover":
        return ImageOps.fit(img, target, method=method)
    return ImageOps.pad(img.convert("RGBA"), target, method=method, color=(0, 0, 0, 0))


def replace_region(base, replacement, x, y, size, fit="cover", resample="lanczos", blend=False):
    """Return a copy of base with the square at (x, y) replaced by replacement.
    With blend, transparent parts of the replacement show the original pixels;
    otherwise the region's pixels (including alpha) are overwritten exactly."""
    x, y, size = clamp_region(base.size, x, y, size)
    patch = fit_square(replacement, size, fit, resample)

    if base.mode == patch.mode:
        mode = base.mode
    elif "A" in base.mode or "A" in patch.mode:
        mode = "RGBA"
    else:
        mode = "RGB"

    out = base.convert(mode) if base.mode != mode else base.copy()
    patch = patch.convert(mode) if patch.mode != mode else patch

    if blend and mode == "RGBA":
        out.alpha_composite(patch, (x, y))
    else:
        out.paste(patch, (x, y))
    out.info.update({k: base.info[k] for k in _META_KEYS if k in base.info})
    return out
