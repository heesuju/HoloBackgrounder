import argparse
import cv2
import numpy as np
from PIL import Image, ImageSequence
import os

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def process_video(input_path, output_path, loop_count, replace_bg=False, bg_color_hex=None, threshold=50, pad_frames=0):
    """
    Converts GIF or WEBM to MP4, optionally replacing background color.
    """
    frames = []
    duration = 100 # Default duration in ms per frame
    fps = 10.0
    width = 0
    height = 0

    input_lower = input_path.lower()
    is_gif = input_lower.endswith('.gif')
    is_webm = input_lower.endswith('.webm')

    if not (is_gif or is_webm):
        raise ValueError("Unsupported input format. Must be .gif or .webm")

    # 1. READ FRAMES
    if is_gif:
        try:
            with Image.open(input_path) as im:
                duration = im.info.get('duration', 100) or 100
                fps = 1000.0 / duration
                
                for frame in ImageSequence.Iterator(im):
                    # Convert to RGBA for consistent processing
                    frame = frame.convert("RGBA")
                    # Convert to numpy array (RGB) - we handle alpha blending manually if needed, 
                    # but for MP4 (no alpha), we usually blend with black or white. 
                    # Here we want to replace a specific color first.
                    
                    # Convert PIL to numpy array (H, W, 4)
                    frame_np = np.array(frame)
                    frames.append(frame_np)
        except Exception as e:
            raise Exception(f"Error opening GIF: {e}")
            
    elif is_webm:
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception(f"Could not open WEBM file: {input_path}")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 24.0 # Fallback
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            # cv2 reads as BGR, convert to RGBA (to match GIF logic structure)
            # We add an alpha channel of 255 (opaque) for consistency in processing
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            frames.append(frame_rgb)
        
        cap.release()

    original_frame_count = len(frames)
    if original_frame_count == 0:
        raise Exception("No frames found/extracted from input.")

    height, width, channels = frames[0].shape
    print(f"Input: {input_path}, Frames: {original_frame_count}, Res: {width}x{height}, FPS: {fps:.2f}")

    # 2. PREPARE OUTPUT VIDEO
    total_output_frames = int(original_frame_count * loop_count)
    print(f"Loop count: {loop_count}, Total output frames: {total_output_frames}")

    # Verify openCV availability
    if not cv2:
        raise Exception("OpenCV (cv2) not available.")
        
    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
    video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    if not video.isOpened():
        raise Exception(f"Could not open VideoWriter for {output_path}")

    # Prepare target color for replacement
    target_bg_rgb = None
    if replace_bg and bg_color_hex:
        target_bg_rgb = hex_to_rgb(bg_color_hex)
        print(f"Replacing background color {bg_color_hex} {target_bg_rgb} with BLACK (threshold {threshold})")

    # 3. PROCESS AND WRITE FRAMES
    
    # Helper function to process and write a frame
    def write_frame_to_video(frame_source):
        # frame_source is numpy array (H, W, 4) - RGBA
        current_frame = frame_source.copy() # Copy to avoid modifying original

        # --- Background Replacement Logic ---
        if replace_bg and target_bg_rgb:
            # Extract RGB for comparison
            # current_frame is numpy array [H, W, 4] (R, G, B, A)
            rgb_part = current_frame[:, :, :3]
            
            # Calculate Euclidean distance to target_color
            diff = rgb_part.astype(np.int32) - np.array(target_bg_rgb, dtype=np.int32)
            dist_sq = np.sum(diff**2, axis=2) # (H, W)
            
            # Create mask where distance is within threshold
            dist = np.sqrt(dist_sq)
            mask = dist <= threshold
            
            # Apply mask: Set matching pixels to Black (0, 0, 0, 255)
            current_frame[mask] = [0, 0, 0, 255]

        # --- Convert to format for VideoWriter ---
        # VideoWriter expects BGR (and no Alpha usually, unless supported, but mp4v is usually just 3 channels)
        # We will flatten alpha to black if transparency exists, effectively making transparent parts black
        
        alpha = current_frame[:, :, 3] / 255.0
        alpha = np.expand_dims(alpha, axis=2) # (H, W, 1)
        
        foreground_rgb = current_frame[:, :, :3]
        
        # Alpha blending: out = alpha * foreground + (1 - alpha) * background
        # Since background is black (0), it simplifies to: out = alpha * foreground
        blended = (alpha * foreground_rgb).astype(np.uint8)
        
        # Convert RGB to BGR for OpenCV
        out_frame_bgr = cv2.cvtColor(blended, cv2.COLOR_RGB2BGR)
        
        video.write(out_frame_bgr)
        return 1

    frames_written = 0
    # Main Loop
    for i in range(total_output_frames):
        # Calculate frame index (modulo for looping)
        frame_idx = i % original_frame_count
        frames_written += write_frame_to_video(frames[frame_idx])

    # Pad Frames Loop
    if pad_frames > 0:
        print(f"Padding with {pad_frames} extra copies of the last frame.")
        # If possible, reuse the very last frame sent to video (after processing)
        # But since write_frame_to_video recalculates everything, we can just call it again
        # with the last frame from source list.
        # Note: if loop_count is fractional, total_output_frames might end mid-way.
        # But 'last frame' usually implies the last frame of the *loop cycle* or the last frame *written*?
        # User wants to prevent skipping on loop restart, so extending the video with the last visible frame makes sense.
        
        last_frame_idx = (total_output_frames - 1) % original_frame_count
        last_frame_source = frames[last_frame_idx]
        
        for _ in range(pad_frames):
            frames_written += write_frame_to_video(last_frame_source)

    video.release()
    print(f"Saved MP4 to {output_path} (Total frames: {frames_written})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert GIF/WEBM to MP4 with loop control and BG replacement.")
    parser.add_argument("input_file", help="Path to input GIF or WEBM file")
    parser.add_argument("output_mp4", help="Path to output MP4 file")
    parser.add_argument("loop_count", type=float, help="Loop count (float, e.g., 1.5)")
    parser.add_argument("--replace_bg", action="store_true", help="Enable background color replacement")
    parser.add_argument("--bg_color", help="Hex color of the background to remove (e.g., #FFFFFF)")
    parser.add_argument("--threshold", type=int, default=50, help="Threshold for color matching")
    parser.add_argument("--pad_frames", type=int, default=0, help="Number of extra frames to append at the end")

    args = parser.parse_args()
    
    process_video(
        args.input_file, 
        args.output_mp4, 
        args.loop_count, 
        replace_bg=args.replace_bg, 
        bg_color_hex=args.bg_color, 
        threshold=args.threshold,
        pad_frames=args.pad_frames
    )
