from PIL import Image

ICON_SIZES = (16, 32, 48, 128)


def has_alpha(img):
    if img.mode in ("RGBA", "LA"):
        return True
    if img.mode == "P" and "transparency" in img.info:
        return True
    return False


def prepare_square_source(img):
    """Return a 1:1 version of img, padding (never cropping) to preserve all
    content. Keeps/adds an alpha channel only if the source already had one,
    so transparency is preserved but never forced onto an opaque image."""
    alpha = has_alpha(img)
    img = img.convert("RGBA") if alpha else img.convert("RGB")

    w, h = img.size
    if w == h:
        return img, alpha

    side = max(w, h)
    offset = ((side - w) // 2, (side - h) // 2)
    if alpha:
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, offset, img)
    else:
        canvas = Image.new("RGB", (side, side), (255, 255, 255))
        canvas.paste(img, offset)
    return canvas, alpha


def generate_icons(image, sizes=ICON_SIZES):
    """Generate square icon versions of `image` (a path or PIL Image) at each
    size in `sizes`, using the highest-quality resampling and preserving the
    source's alpha channel if it has one. Returns {size: PIL.Image}."""
    img = Image.open(image) if isinstance(image, str) else image
    square_img, alpha = prepare_square_source(img)

    results = {}
    for size in sizes:
        results[size] = square_img.resize((size, size), Image.Resampling.LANCZOS)
    return results, alpha
