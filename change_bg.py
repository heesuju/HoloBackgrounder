import argparse
from PIL import Image, ImageSequence
import math

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def color_distance_sq(c1, c2):
    # Euclidean distance squared (faster than sqrt and sufficient for comparison if threshold is squared)
    # But for a simple threshold (int) requested by user, let's stick to a simple Euclidean distance or similar.
    # The user manual says "threshold (int) for detecting whether colors are same".
    # Typically this means Euclidean distance < threshold.
    return math.sqrt(sum((c1[i] - c2[i]) ** 2 for i in range(3)))

def change_background(input_path, output_path, bg_color_hex, threshold):
    target_bg = hex_to_rgb(bg_color_hex)
    print(f"Target background color: {target_bg} (from {bg_color_hex}) with threshold {threshold}")

    try:
        im = Image.open(input_path)
    except Exception as e:
        raise Exception(f"Error opening file: {e}")

    frames = []
    # Preserve duration and loop if possible. 
    duration = im.info.get('duration', 100)
    loop = im.info.get('loop', 0)
    
    frame_count = 0
    for frame in ImageSequence.Iterator(im):
        frame_count += 1
        # Convert to RGBA to ensure we have alpha channel and consistent color space
        frame = frame.convert("RGBA")
        datas = frame.getdata()

        new_data = []
        for item in datas:
            # item is (r, g, b, a)
            # Compare RGB part
            current_color = item[:3]
            dist = color_distance_sq(current_color, target_bg)
            
            if dist <= threshold:
                # Change to black (0, 0, 0) and keep alpha 255 (opaque)
                new_data.append((0, 0, 0, 255))
            else:
                new_data.append(item)

        frame.putdata(new_data)
        frames.append(frame)

    if frames:
        frames[0].save(output_path, saved_all=True, append_images=frames[1:], optimize=False, duration=duration, loop=loop)
        print(f"Processed {frame_count} frames.")
        print(f"Saved output to {output_path}")
        return frame_count
    else:
        raise Exception("No frames found to save.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Change GIF background color to black.")
    parser.add_argument("input_file", help="Path to input GIF file")
    parser.add_argument("output_file", help="Path to output GIF file")
    parser.add_argument("hex_color", help="Hex color of the background to remove (e.g., #FFFFFF)")
    parser.add_argument("threshold", type=int, help="Threshold for color matching (integer)")

    args = parser.parse_args()
    change_background(args.input_file, args.output_file, args.hex_color, args.threshold)
