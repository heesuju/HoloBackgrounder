import os
import cv2
import numpy as np
from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QFileDialog, QGroupBox, QFormLayout, QMessageBox, QColorDialog)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap, QColor, QBrush, QPainter

class ResizableGraphicsView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene() and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

class OutlineTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        self.original_np = None # original RGBA array
        self.current_display_qimage = None
        
        self.outline_color = np.array([255, 255, 255], dtype=np.uint8)
        self.thickness = 10
        self.softness = 0
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        controls_group = QGroupBox("Outline Settings")
        controls_layout = QHBoxLayout()
        
        # Tools
        tools_layout = QVBoxLayout()
        self.btn_color = QPushButton("Choose Outline Color")
        self.btn_color.clicked.connect(self.choose_color)
        tools_layout.addWidget(self.btn_color)
        controls_layout.addLayout(tools_layout)

        # Sliders and Pickers
        sliders_layout = QFormLayout()
        
        # Color indicator
        self.color_indicator = QLabel()
        self.color_indicator.setFixedSize(30, 30)
        self.color_indicator.setStyleSheet(f"background-color: rgb(255, 255, 255); border: 1px solid black;")
        
        color_btn_layout = QHBoxLayout()
        color_btn_layout.addWidget(self.color_indicator)
        color_btn_layout.addStretch()
        sliders_layout.addRow("Current Color:", color_btn_layout)

        self.thickness_slider = QSlider(Qt.Orientation.Horizontal)
        self.thickness_slider.setRange(0, 100)
        self.thickness_slider.setValue(self.thickness)
        self.thickness_slider.valueChanged.connect(self.on_thickness_changed)
        sliders_layout.addRow("Thickness:", self.thickness_slider)

        self.softness_slider = QSlider(Qt.Orientation.Horizontal)
        self.softness_slider.setRange(0, 100)
        self.softness_slider.setValue(self.softness)
        self.softness_slider.valueChanged.connect(self.on_softness_changed)
        sliders_layout.addRow("Softness (Gradient):", self.softness_slider)
        
        controls_layout.addLayout(sliders_layout)
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Image View
        self.view = ResizableGraphicsView()
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        # Checkerboard background
        bg_pixmap = self.create_checkerboard_pattern()
        self.view.setBackgroundBrush(QBrush(bg_pixmap))
        layout.addWidget(self.view)

    def create_checkerboard_pattern(self):
        size = 20
        img = QImage(size * 2, size * 2, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        painter.fillRect(0, 0, size, size, QColor(200, 200, 200))
        painter.fillRect(size, size, size, size, QColor(200, 200, 200))
        painter.fillRect(size, 0, size, size, QColor(150, 150, 150))
        painter.fillRect(0, size, size, size, QColor(150, 150, 150))
        painter.end()
        return QPixmap.fromImage(img)

    def on_global_files_changed(self):
        valid_file = self.get_valid_file()
        if valid_file:
            self.load_image_from_path(valid_file)
        else:
            self.clear_image()

    def get_valid_file(self):
        for f in self.main_window.current_files:
            if f.lower().endswith(('.png', '.webp')):
                return f
        return None

    def load_image_from_path(self, file_path):
        if file_path:
            try:
                # Load with PIL and convert to RGBA
                img = Image.open(file_path).convert("RGBA")
                self.original_np = np.array(img) # Shape: (H, W, 4)
                
                h, w = self.original_np.shape[:2]
                self.scene.setSceneRect(0, 0, w, h)
                self.main_window.set_export_enabled(True)
                
                self.update_display()
                self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load image: {e}")

    def clear_image(self):
        self.original_np = None
        self.current_display_qimage = None
        self.pixmap_item.setPixmap(QPixmap())
        self.main_window.set_export_enabled(False)
        self.scene.setSceneRect(0, 0, 0, 0)

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.outline_color[0], self.outline_color[1], self.outline_color[2]))
        if color.isValid():
            self.outline_color = np.array([color.red(), color.green(), color.blue()], dtype=np.uint8)
            self.color_indicator.setStyleSheet(f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); border: 1px solid black;")
            self.update_display()

    def on_thickness_changed(self, value):
        self.thickness = value
        self.update_display()

    def on_softness_changed(self, value):
        self.softness = value
        self.update_display()

    def update_display(self):
        if self.original_np is None:
            return
            
        img_np = self.original_np.copy()
        alpha = img_np[:, :, 3]
        
        # 1. Dilation (Thickness)
        if self.thickness > 0:
            ksize = 2 * self.thickness + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
            outline_alpha = cv2.dilate(alpha, kernel, iterations=1)
        else:
            outline_alpha = alpha.copy()
            
        # 2. Softness (Gradient)
        if self.softness > 0:
            ksize = 2 * self.softness + 1
            outline_alpha = cv2.GaussianBlur(outline_alpha, (ksize, ksize), 0)
            
        # Composite: Original image OVER the generated outline
        img_f = img_np.astype(np.float32) / 255.0
        
        # Create full outline image
        outline_f = np.zeros_like(img_f)
        outline_f[..., :3] = self.outline_color.astype(np.float32) / 255.0
        outline_f[..., 3] = outline_alpha.astype(np.float32) / 255.0
        
        # Alpha compositing formula:
        # out_a = src_a + dst_a * (1 - src_a)
        # out_rgb = (src_rgb * src_a + dst_rgb * dst_a * (1 - src_a)) / out_a
        
        src_a = img_f[..., 3:4]
        dst_a = outline_f[..., 3:4]
        
        out_a = src_a + dst_a * (1.0 - src_a)
        
        out_rgb = np.zeros_like(img_f[..., :3])
        mask = out_a[..., 0] > 0
        
        out_rgb[mask] = (img_f[..., :3][mask] * src_a[mask] + outline_f[..., :3][mask] * dst_a[mask] * (1.0 - src_a[mask])) / out_a[mask]
        
        result_np = np.zeros_like(img_np)
        result_np[..., :3] = (out_rgb * 255).astype(np.uint8)
        result_np[..., 3] = (out_a[..., 0] * 255).astype(np.uint8)

        h, w, ch = result_np.shape
        bytes_per_line = ch * w
        
        # We must keep a reference to current_np so the memory is not garbage collected
        qimg = QImage(result_np.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
        self.current_display_qimage = qimg.copy()
            
        self.pixmap_item.setPixmap(QPixmap.fromImage(self.current_display_qimage))

    def export(self):
        if self.current_display_qimage is None:
            return
            
        base_name = self.main_window.override_name_input.text().strip()
        start_index = self.main_window.start_index_input.value()
        default_name = f"{base_name}_{start_index}.png" if base_name else "outlined_image.png"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Image", default_name, "PNG Images (*.png)")
        if file_path:
            self.current_display_qimage.save(file_path, "PNG")
            self.main_window.set_status(f"Saved to {file_path}")
            QMessageBox.information(self, "Success", f"Saved to {file_path}")
