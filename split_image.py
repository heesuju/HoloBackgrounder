import cv2
import numpy as np
import os

def split_and_save_shapes(input_path, output_dir=None, min_area=50, min_alpha=10):
    """
    Reads an image with an alpha channel, identifies disconnected shapes
    based on the alpha channel, and saves each shape as a separate tightly-cropped PNG.
    """
    if output_dir is None:
        output_dir = os.path.dirname(input_path)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Read the image with alpha channel
    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Could not read image at {input_path}")
        
    if len(img.shape) < 3 or img.shape[2] != 4:
        raise ValueError("Image does not have an alpha channel (must be RGBA).")
        
    # Extract alpha channel
    alpha = img[:, :, 3]
    
    # Threshold to create a binary mask (alpha >= min_alpha)
    _, binary_mask = cv2.threshold(alpha, max(0, min_alpha - 1), 255, cv2.THRESH_BINARY)
    
    # Find connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    
    saved_files = []
    
    # label 0 is the background
    for i in range(1, num_labels):
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        
        # Skip small noise/artifacts
        if area < min_area:
            continue
            
        # Create a mask for this specific component
        component_mask = (labels == i).astype(np.uint8) * 255
        
        # Crop the mask and the original image to the bounding box
        cropped_mask = component_mask[y:y+h, x:x+w]
        cropped_img = img[y:y+h, x:x+w].copy()
        
        # Apply the cropped mask to the alpha channel of the cropped image
        # This ensures overlapping bounding boxes from other shapes are masked out
        cropped_img[:, :, 3] = cv2.bitwise_and(cropped_img[:, :, 3], cropped_mask)
        
        output_filename = f"{base_name}_part_{i}.png"
        output_path = os.path.join(output_dir, output_filename)
        
        cv2.imwrite(output_path, cropped_img)
        saved_files.append(output_path)
        
    return saved_files
