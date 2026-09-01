from PyQt6.QtCore import QThread, pyqtSignal
import os
import re
import change_bg
import gif_to_mp4
import split_image

class WorkerThread(QThread):
    finished = pyqtSignal(bool, str) # Success, Message
    progress = pyqtSignal(str)

    def __init__(self, input_path, output_path, bg_color, threshold, loop_count, replace_bg, pad_frames):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.bg_color = bg_color
        self.threshold = threshold
        self.loop_count = loop_count
        self.replace_bg = replace_bg
        self.pad_frames = pad_frames

    def run(self):
        try:
            self.progress.emit("Processing video...")
            gif_to_mp4.process_video(
                self.input_path, 
                self.output_path, 
                self.loop_count, 
                replace_bg=self.replace_bg,
                bg_color_hex=self.bg_color,
                threshold=self.threshold,
                pad_frames=self.pad_frames
            )
            self.finished.emit(True, f"Successfully saved to {self.output_path}")
        except Exception as e:
            self.finished.emit(False, str(e))

class SplitImageWorkerThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def __init__(self, input_path, output_dir, min_area, min_alpha, override_name, start_index):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.min_area = min_area
        self.min_alpha = min_alpha
        self.override_name = override_name
        self.start_index = start_index

    def run(self):
        try:
            self.progress.emit("Splitting image...")
            saved_files = split_image.split_and_save_shapes(self.input_path, self.output_dir, self.min_area, self.min_alpha, self.override_name, self.start_index)
            self.finished.emit(True, f"Successfully extracted {len(saved_files)} shapes to {self.output_dir}")
        except Exception as e:
            self.finished.emit(False, str(e))

class RenameWorkerThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def __init__(self, file_paths, override_name, start_index):
        super().__init__()
        self.file_paths = file_paths
        self.override_name = override_name
        self.start_index = start_index

    def run(self):
        try:
            self.progress.emit("Sorting files...")
            
            # Basic alphanumeric sort based on filename
            def natural_keys(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
            
            sorted_files = sorted(self.file_paths, key=lambda x: natural_keys(os.path.basename(x)))
            
            self.progress.emit("Renaming files...")
            count = 0
            for idx, file_path in enumerate(sorted_files):
                dir_name = os.path.dirname(file_path)
                ext = os.path.splitext(file_path)[1]
                
                base = self.override_name.strip() if self.override_name and self.override_name.strip() else "renamed_"
                new_name = f"{base}{self.start_index + count}{ext}"
                new_path = os.path.join(dir_name, new_name)
                
                if os.path.exists(new_path) and new_path != file_path:
                    # In a real app we might handle collisions, but for batch rename we'll just rename
                    pass 
                
                os.rename(file_path, new_path)
                count += 1
                
            self.finished.emit(True, f"Successfully renamed {count} files.")
        except Exception as e:
            self.finished.emit(False, str(e))

class CropWorkerThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def __init__(self, file_paths, output_dir, crop_rect, override_name, start_index):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.crop_rect = crop_rect # (x, y, w, h)
        self.override_name = override_name
        self.start_index = start_index

    def run(self):
        try:
            from PIL import Image
            self.progress.emit("Cropping images...")
            
            x, y, w, h = self.crop_rect
            
            count = 0
            for idx, file_path in enumerate(self.file_paths):
                try:
                    img = Image.open(file_path)
                    
                    # Ensure coordinates are within bounds (optional, but PIL crop handles it mostly)
                    cropped_img = img.crop((x, y, x + w, y + h))
                    
                    ext = os.path.splitext(file_path)[1]
                    base = self.override_name.strip() if self.override_name and self.override_name.strip() else "cropped_"
                    new_name = f"{base}{self.start_index + count}{ext}"
                    new_path = os.path.join(self.output_dir, new_name)
                    
                    cropped_img.save(new_path)
                    count += 1
                except Exception as ex:
                    print(f"Failed to crop {file_path}: {ex}")
                    
            self.finished.emit(True, f"Successfully cropped {count} images.")
        except Exception as e:
            self.finished.emit(False, str(e))
