import os
import cv2
import numpy as np
from PIL import Image, ImageSequence

SUPPORTED_VIDEO_EXTS = ('.mp4', '.webm', '.avi', '.mov', '.mkv', '.m4v', '.wmv', '.gif')

def is_gif_file(file_path):
    return file_path.lower().endswith('.gif')

def get_media_info(file_path):
    """
    Returns metadata dict for a video or GIF file:
    {
        'path': file_path,
        'filename': basename,
        'is_gif': bool,
        'width': int,
        'height': int,
        'fps': float,
        'total_frames': int,
        'duration': float, # seconds
    }
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = os.path.basename(file_path)
    is_gif = is_gif_file(file_path)

    if is_gif:
        try:
            with Image.open(file_path) as im:
                width, height = im.size
                total_frames = getattr(im, 'n_frames', 1)
                
                # Calculate average duration
                durations = []
                for i in range(min(total_frames, 50)):
                    im.seek(i)
                    d = im.info.get('duration', 100) or 100
                    durations.append(d)
                
                avg_dur_ms = sum(durations) / len(durations) if durations else 100.0
                fps = 1000.0 / avg_dur_ms if avg_dur_ms > 0 else 10.0
                total_duration = (total_frames * avg_dur_ms) / 1000.0

                return {
                    'path': file_path,
                    'filename': filename,
                    'is_gif': True,
                    'width': width,
                    'height': height,
                    'fps': round(fps, 2),
                    'total_frames': total_frames,
                    'duration': round(total_duration, 2),
                }
        except Exception as e:
            raise ValueError(f"Error reading GIF info: {e}")
    else:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {file_path}")
        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0 or np.isnan(fps):
                fps = 24.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = (total_frames / fps) if (total_frames > 0 and fps > 0) else 0.0

            return {
                'path': file_path,
                'filename': filename,
                'is_gif': False,
                'width': width,
                'height': height,
                'fps': round(fps, 2),
                'total_frames': max(1, total_frames),
                'duration': round(duration, 2),
            }
        finally:
            cap.release()

def get_frame_at_index(file_path, frame_index):
    """
    Retrieves a single frame by 0-based frame index as a PIL Image (RGBA or RGB)
    along with timestamp in seconds.
    """
    if is_gif_file(file_path):
        with Image.open(file_path) as im:
            total = getattr(im, 'n_frames', 1)
            idx = max(0, min(frame_index, total - 1))
            im.seek(idx)
            # Compose RGBA
            frame_img = im.convert('RGBA')
            duration_ms = im.info.get('duration', 100) or 100
            timestamp = (idx * duration_ms) / 1000.0
            return frame_img.copy(), timestamp
    else:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None, 0.0
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            if not ret or frame is None:
                return None, 0.0
            fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            timestamp = frame_index / fps if fps > 0 else 0.0
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb), timestamp
        finally:
            cap.release()

def calculate_frame_difference(img_a, img_b):
    """
    Calculates the normalized difference percentage (0.0 to 100.0)
    between two PIL Images.
    Uses cv2.absdiff on uint8 arrays for maximum speed.
    """
    if img_a is None or img_b is None:
        return 100.0

    arr_a = np.asarray(img_a)
    arr_b = np.asarray(img_b)

    if arr_a.shape != arr_b.shape:
        # Resize B to match A if dimension mismatch
        img_b_resized = img_b.resize(img_a.size, Image.Resampling.NEAREST)
        arr_b = np.asarray(img_b_resized)

    # Check exact match first
    if np.array_equal(arr_a, arr_b):
        return 0.0

    diff = cv2.absdiff(arr_a, arr_b)
    mean_val = float(np.mean(diff))
    diff_pct = (mean_val / 255.0) * 100.0
    return diff_pct

def scan_different_frames(file_path, mode='consecutive', threshold=1.0, step=1,
                          max_thumb_size=(96, 96), progress_callback=None, cancel_event=None):
    """
    Scans a video or GIF and returns a list of distinct frame metadata:
    [
        {
            'index': int,
            'timestamp': float,
            'diff_pct': float,
            'thumbnail': PIL.Image,
        },
        ...
    ]
    mode: 'consecutive' (skip identical consecutive frames),
          'global' (skip if duplicate of ANY earlier kept frame),
          'all' (keep all sampled frames)
    threshold: difference percentage (0.0 to 100.0)
    """
    is_gif = is_gif_file(file_path)
    kept_items = []
    
    # Structure for global comparison: thumbnail cache
    kept_thumbs_matrix = [] # list of small (32, 32, C) uint8 arrays
    prev_frame_arr = None

    if is_gif:
        with Image.open(file_path) as im:
            total_frames = getattr(im, 'n_frames', 1)
            time_accum = 0.0

            for idx in range(0, total_frames, max(1, step)):
                if cancel_event and cancel_event.is_set():
                    break

                im.seek(idx)
                frame = im.convert('RGBA')
                frame_arr = np.asarray(frame)
                dur = im.info.get('duration', 100) or 100
                timestamp = time_accum
                time_accum += (dur * max(1, step)) / 1000.0

                is_diff, diff_val = _eval_frame_difference(
                    frame_arr, prev_frame_arr, kept_thumbs_matrix, mode, threshold
                )

                if is_diff:
                    # Create thumbnail for preview
                    thumb = frame.copy()
                    thumb.thumbnail(max_thumb_size, Image.Resampling.BILINEAR)

                    kept_items.append({
                        'index': idx,
                        'timestamp': timestamp,
                        'diff_pct': round(diff_val, 2),
                        'thumbnail': thumb,
                    })

                    prev_frame_arr = frame_arr
                    if mode == 'global':
                        small_thumb = cv2.resize(frame_arr, (32, 32), interpolation=cv2.INTER_AREA)
                        kept_thumbs_matrix.append(small_thumb)

                if progress_callback:
                    progress_callback(idx + 1, total_frames, len(kept_items))

    else:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return []
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            idx = 0

            while True:
                if cancel_event and cancel_event.is_set():
                    break

                ret, frame_bgr = cap.read()
                if not ret or frame_bgr is None:
                    break

                if idx % max(1, step) == 0:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    timestamp = idx / fps if fps > 0 else 0.0

                    is_diff, diff_val = _eval_frame_difference(
                        frame_rgb, prev_frame_arr, kept_thumbs_matrix, mode, threshold
                    )

                    if is_diff:
                        pil_frame = Image.fromarray(frame_rgb)
                        thumb = pil_frame.copy()
                        thumb.thumbnail(max_thumb_size, Image.Resampling.BILINEAR)

                        kept_items.append({
                            'index': idx,
                            'timestamp': timestamp,
                            'diff_pct': round(diff_val, 2),
                            'thumbnail': thumb,
                        })

                        prev_frame_arr = frame_rgb
                        if mode == 'global':
                            small_thumb = cv2.resize(frame_rgb, (32, 32), interpolation=cv2.INTER_AREA)
                            kept_thumbs_matrix.append(small_thumb)

                    if progress_callback:
                        progress_callback(idx + 1, max(idx + 1, total_frames), len(kept_items))

                idx += 1
        finally:
            cap.release()

    return kept_items

def _eval_frame_difference(frame_arr, prev_frame_arr, kept_thumbs_matrix, mode, threshold):
    """
    Helper function to determine if a frame is different based on mode and threshold.
    Returns (is_diff: bool, diff_pct: float).
    """
    if prev_frame_arr is None:
        return True, 100.0

    if mode == 'all':
        return True, 100.0

    if mode == 'consecutive':
        if threshold <= 0.0:
            if np.array_equal(frame_arr, prev_frame_arr):
                return False, 0.0
            return True, 100.0
        
        diff = cv2.absdiff(frame_arr, prev_frame_arr)
        mean_val = float(np.mean(diff))
        diff_pct = (mean_val / 255.0) * 100.0
        return (diff_pct >= threshold), diff_pct

    elif mode == 'global':
        if not kept_thumbs_matrix:
            return True, 100.0

        # Fast vector thumbnail test
        small_cand = cv2.resize(frame_arr, (32, 32), interpolation=cv2.INTER_AREA)
        thumbs_stack = np.stack(kept_thumbs_matrix)
        
        # Mean absolute difference against all kept thumbnails
        diffs = np.mean(
            np.abs(thumbs_stack.astype(np.int16) - small_cand.astype(np.int16)),
            axis=(1, 2, 3)
        ) / 2.55

        min_diff = float(np.min(diffs))
        if threshold <= 0.0:
            # If thumbnail matched with 0 diff, check exact array against prev or matching
            if min_diff < 0.01:
                return False, 0.0
            return True, min_diff
        else:
            if min_diff < threshold:
                # Close match found in previously kept frames, skip!
                return False, min_diff
            return True, min_diff

    return True, 100.0

def extract_different_frames_to_disk(
    file_path,
    output_dir,
    mode='consecutive',
    threshold=1.0,
    step=1,
    output_format='png',
    jpeg_quality=95,
    base_name=None,
    start_index=1,
    zero_pad=-1,
    create_subfolder=True,
    progress_callback=None,
    cancel_event=None
):
    """
    Extracts distinct frames from a video/gif directly to disk.
    Returns:
    {
        'saved_files': list of saved file paths,
        'output_dir': actual directory where files were saved,
        'total_processed': total frames scanned,
        'total_extracted': count of frames saved,
    }
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    stem = os.path.splitext(os.path.basename(file_path))[0]
    
    if create_subfolder:
        target_dir = os.path.join(output_dir, f"{stem}_frames")
    else:
        target_dir = output_dir

    os.makedirs(target_dir, exist_ok=True)

    info = get_media_info(file_path)
    total_frames = info['total_frames']

    if zero_pad < 0:
        # Auto calculate padding: e.g. 100 frames -> 3 digits
        zero_pad = max(4, len(str(total_frames + start_index)))

    prefix = base_name.strip() if (base_name and base_name.strip()) else f"{stem}_frame_"
    ext = output_format.lower().lstrip('.')
    if ext == 'jpeg': ext = 'jpg'

    saved_files = []
    saved_count = 0
    prev_frame_arr = None
    kept_thumbs_matrix = []
    is_gif = is_gif_file(file_path)

    def save_image_frame(pil_img, current_idx):
        nonlocal saved_count
        idx_num = start_index + saved_count
        if zero_pad > 0:
            idx_str = f"{idx_num:0{zero_pad}d}"
        else:
            idx_str = str(idx_num)

        out_name = f"{prefix}{idx_str}.{ext}"
        out_path = os.path.join(target_dir, out_name)

        # Handle format details
        if ext in ('jpg', 'jpeg'):
            if pil_img.mode in ('RGBA', 'LA') or (pil_img.mode == 'P' and 'transparency' in pil_img.info):
                bg = Image.new('RGB', pil_img.size, (255, 255, 255))
                bg.paste(pil_img, mask=pil_img.convert('RGBA').split()[3])
                bg.save(out_path, 'JPEG', quality=jpeg_quality)
            else:
                pil_img.convert('RGB').save(out_path, 'JPEG', quality=jpeg_quality)
        elif ext == 'webp':
            pil_img.save(out_path, 'WEBP', quality=jpeg_quality)
        else:
            pil_img.save(out_path)

        saved_files.append(out_path)
        saved_count += 1
        return out_path

    if is_gif:
        with Image.open(file_path) as im:
            n_frames = getattr(im, 'n_frames', 1)
            for idx in range(0, n_frames, max(1, step)):
                if cancel_event and cancel_event.is_set():
                    break

                im.seek(idx)
                frame = im.convert('RGBA')
                frame_arr = np.asarray(frame)

                is_diff, _ = _eval_frame_difference(
                    frame_arr, prev_frame_arr, kept_thumbs_matrix, mode, threshold
                )

                if is_diff:
                    saved_path = save_image_frame(frame, idx)
                    prev_frame_arr = frame_arr
                    if mode == 'global':
                        kept_thumbs_matrix.append(
                            cv2.resize(frame_arr, (32, 32), interpolation=cv2.INTER_AREA)
                        )
                else:
                    saved_path = None

                if progress_callback:
                    progress_callback(idx + 1, n_frames, saved_count, saved_path)
    else:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {file_path}")
        try:
            idx = 0
            while True:
                if cancel_event and cancel_event.is_set():
                    break

                ret, frame_bgr = cap.read()
                if not ret or frame_bgr is None:
                    break

                if idx % max(1, step) == 0:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    is_diff, _ = _eval_frame_difference(
                        frame_rgb, prev_frame_arr, kept_thumbs_matrix, mode, threshold
                    )

                    if is_diff:
                        pil_frame = Image.fromarray(frame_rgb)
                        saved_path = save_image_frame(pil_frame, idx)
                        prev_frame_arr = frame_rgb
                        if mode == 'global':
                            kept_thumbs_matrix.append(
                                cv2.resize(frame_rgb, (32, 32), interpolation=cv2.INTER_AREA)
                            )
                    else:
                        saved_path = None

                    if progress_callback:
                        progress_callback(idx + 1, max(idx + 1, total_frames), saved_count, saved_path)

                idx += 1
        finally:
            cap.release()

    return {
        'saved_files': saved_files,
        'output_dir': target_dir,
        'total_processed': total_frames,
        'total_extracted': saved_count,
    }
