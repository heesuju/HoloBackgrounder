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

    def __init__(self, file_paths, override_name, start_index, order_by="Name (Alphanumerical)"):
        super().__init__()
        self.file_paths = file_paths
        self.override_name = override_name
        self.start_index = start_index
        self.order_by = order_by

    def run(self):
        try:
            self.progress.emit("Sorting files...")
            
            if self.order_by == "Date Created":
                sorted_files = sorted(self.file_paths, key=lambda x: os.path.getctime(x))
            elif self.order_by == "Date Modified":
                sorted_files = sorted(self.file_paths, key=lambda x: os.path.getmtime(x))
            else:
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

    def __init__(self, file_paths, output_dir, crop_rect, override_name, start_index, center=False):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.crop_rect = crop_rect # (x, y, w, h)
        self.center = center # if True, ignore x/y and center the crop on each image
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
                    if self.center:
                        x = (img.width - w) // 2
                        y = (img.height - h) // 2

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

class PdfWorkerThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def __init__(self, file_paths, output_path):
        super().__init__()
        self.file_paths = file_paths
        self.output_path = output_path

    def run(self):
        try:
            self.progress.emit("Creating PDF...")
            from PIL import Image
            
            if not self.file_paths:
                self.finished.emit(False, "No files to process.")
                return

            images = []
            first_image = None
            
            count = 0
            for idx, file_path in enumerate(self.file_paths):
                try:
                    img = Image.open(file_path).convert('RGB')
                    if idx == 0:
                        first_image = img
                    else:
                        images.append(img)
                    count += 1
                except Exception as ex:
                    print(f"Failed to open {file_path}: {ex}")
            
            if first_image:
                first_image.save(self.output_path, "PDF" ,resolution=100.0, save_all=True, append_images=images, quality=100)
                self.finished.emit(True, f"Successfully created PDF with {count} pages.")
            else:
                self.finished.emit(False, "Failed to open any valid images.")
        except Exception as e:
            self.finished.emit(False, str(e))

class PixelWorkerThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def __init__(self, file_paths, output_dir, pixel_size, num_colors, dither, crisp_alpha, output_scale, override_name, start_index):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.pixel_size = pixel_size
        self.num_colors = num_colors
        self.dither = dither
        self.crisp_alpha = crisp_alpha
        self.output_scale = output_scale
        self.override_name = override_name
        self.start_index = start_index

    def run(self):
        try:
            import pixel_art
            self.progress.emit("Pixelating images...")
            count = 0
            total = len(self.file_paths)
            for idx, file_path in enumerate(self.file_paths):
                try:
                    self.progress.emit(f"Processing ({idx + 1}/{total}): {os.path.basename(file_path)}")
                    
                    effective_size = self.pixel_size
                    if effective_size == 'auto' or effective_size == 'recommend':
                        effective_size = pixel_art.recommend_pixel_size(file_path)
                    
                    result_img, _ = pixel_art.process_pixel_art(
                        file_path,
                        target_pixel_size=effective_size,
                        num_colors=self.num_colors,
                        dither=self.dither,
                        crisp_alpha=self.crisp_alpha,
                        output_scale=self.output_scale
                    )
                    
                    ext = os.path.splitext(file_path)[1]
                    if ext.lower() not in ('.png', '.webp', '.jpg', '.jpeg', '.bmp'):
                        ext = '.png'
                        
                    base = self.override_name.strip() if self.override_name and self.override_name.strip() else "pixel_"
                    new_name = f"{base}{self.start_index + count}{ext}"
                    new_path = os.path.join(self.output_dir, new_name)
                    
                    result_img.save(new_path)
                    count += 1
                except Exception as ex:
                    print(f"Failed to pixelate {file_path}: {ex}")
                    
            self.finished.emit(True, f"Successfully pixelated {count} images.")
        except Exception as e:
            self.finished.emit(False, str(e))

class FrameExtractWorkerThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    item_progress = pyqtSignal(int, int, int) # current_frame, total_frames, saved_count

    def __init__(self, file_paths, output_dir, mode='consecutive', threshold=1.0,
                 step=1, output_format='png', jpeg_quality=95, base_name=None,
                 start_index=1, zero_pad=-1, create_subfolder=True):
        super().__init__()
        import threading
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.mode = mode
        self.threshold = threshold
        self.step = step
        self.output_format = output_format
        self.jpeg_quality = jpeg_quality
        self.base_name = base_name
        self.start_index = start_index
        self.zero_pad = zero_pad
        self.create_subfolder = create_subfolder
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            import frame_extractor
            total_files = len(self.file_paths)
            total_extracted = 0
            saved_directories = []

            for f_idx, file_path in enumerate(self.file_paths):
                if self.cancel_event.is_set():
                    self.finished.emit(False, "Extraction cancelled by user.")
                    return

                fname = os.path.basename(file_path)
                self.progress.emit(f"Extracting ({f_idx + 1}/{total_files}): {fname}...")

                # If multiple files and user provided an override base_name, suffix with file index
                curr_base_name = self.base_name
                if self.base_name and total_files > 1:
                    curr_base_name = f"{self.base_name}_{f_idx + 1}"

                def on_progress(curr, total, saved, _path):
                    self.item_progress.emit(curr, total, saved)
                    self.progress.emit(f"[{fname}] Frame {curr}/{total} - Saved {saved} unique frames")

                result = frame_extractor.extract_different_frames_to_disk(
                    file_path=file_path,
                    output_dir=self.output_dir,
                    mode=self.mode,
                    threshold=self.threshold,
                    step=self.step,
                    output_format=self.output_format,
                    jpeg_quality=self.jpeg_quality,
                    base_name=curr_base_name,
                    start_index=self.start_index,
                    zero_pad=self.zero_pad,
                    create_subfolder=self.create_subfolder,
                    progress_callback=on_progress,
                    cancel_event=self.cancel_event
                )

                total_extracted += result['total_extracted']
                if result['output_dir'] not in saved_directories:
                    saved_directories.append(result['output_dir'])

            msg = f"Successfully extracted {total_extracted} frames from {total_files} file(s) into:\n" + "\n".join(saved_directories[:3])
            if len(saved_directories) > 3:
                msg += f"\n... and {len(saved_directories) - 3} more folders"
            self.finished.emit(True, msg)
        except Exception as e:
            self.finished.emit(False, str(e))

class FrameScanWorkerThread(QThread):
    scan_finished = pyqtSignal(list, str) # list of items, file_path
    scan_progress = pyqtSignal(int, int)  # current, total

    def __init__(self, file_path, mode='consecutive', threshold=1.0, step=1):
        super().__init__()
        import threading
        self.file_path = file_path
        self.mode = mode
        self.threshold = threshold
        self.step = step
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            import frame_extractor
            def on_progress(curr, total, kept):
                self.scan_progress.emit(curr, total)

            items = frame_extractor.scan_different_frames(
                file_path=self.file_path,
                mode=self.mode,
                threshold=self.threshold,
                step=self.step,
                progress_callback=on_progress,
                cancel_event=self.cancel_event
            )
            if not self.cancel_event.is_set():
                self.scan_finished.emit(items, self.file_path)
        except Exception as e:
            print(f"Error scanning frames: {e}")
            if not self.cancel_event.is_set():
                self.scan_finished.emit([], self.file_path)


