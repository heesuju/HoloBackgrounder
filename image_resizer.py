from PIL import Image, ImageOps

RESAMPLE_FILTERS = {
    "lanczos": Image.Resampling.LANCZOS,
    "bicubic": Image.Resampling.BICUBIC,
    "nearest": Image.Resampling.NEAREST,
}

# Modes PNG stores natively and Pillow can resample without losing precision.
_KEEP_MODES = ("L", "LA", "RGB", "RGBA", "I;16")


def normalize_mode(img):
    """Return img in a PNG-friendly mode, keeping alpha and bit depth where
    possible so the only change is the resize itself."""
    if img.mode in _KEEP_MODES:
        return img
    if img.mode == "P" or img.mode == "PA" or "transparency" in img.info:
        return img.convert("RGBA")
    if img.mode == "1":
        return img.convert("L")
    if img.mode.startswith("I;16") or img.mode in ("I", "F"):
        return img.convert("I;16") if img.mode.startswith("I;16") else img.convert("L")
    if img.mode in ("RGBa", "La"):
        return img.convert("RGBA" if img.mode == "RGBa" else "LA")
    return img.convert("RGBA" if "A" in img.mode else "RGB")


def compute_size(src_size, mode, width=None, height=None, percent=100, keep_aspect=True, driver="width"):
    """Target (w, h). mode is "percent" or "pixels". With keep_aspect in pixel
    mode, only the `driver` dimension ("width"/"height") is used."""
    sw, sh = src_size
    if mode == "percent":
        return max(1, round(sw * percent / 100)), max(1, round(sh * percent / 100))

    if keep_aspect:
        if driver == "height":
            return max(1, round(sw * height / sh)), height
        return width, max(1, round(sh * width / sw))
    return width, height


def resize_image(img, size, resample="lanczos"):
    """Resize `img` to `size` as losslessly as possible: EXIF orientation is
    applied, the colour mode/alpha is kept, and alpha is resampled
    premultiplied (by Pillow) so edges don't get dark halos."""
    img = ImageOps.exif_transpose(img)
    info = {k: img.info[k] for k in ("icc_profile", "dpi") if k in img.info}
    img = normalize_mode(img)

    if img.size != tuple(size):
        out = img.resize(tuple(size), RESAMPLE_FILTERS[resample])
    else:
        out = img.copy()
    out.info.update(info)
    return out


def save_png(img, path):
    params = {"compress_level": 9}
    for key in ("icc_profile", "dpi"):
        if key in img.info:
            params[key] = img.info[key]
    img.save(path, "PNG", **params)
