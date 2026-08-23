import os
import numpy as np
from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QFileDialog, QGroupBox, QFormLayout, QMessageBox, QColorDialog)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush

class ResizableGraphicsView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene() and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

class ImageScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab = parent
        self.is_drawing = False
        self.last_point = None

    def mousePressEvent(self, event):
        if self.tab.original_np is None:
            return
        pos = event.scenePos()
        x, y = int(pos.x()), int(pos.y())
        h, w = self.tab.original_np.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            if self.tab.spoit_active:
                color = self.tab.original_np[y, x, :3] # RGB
                self.tab.set_target_color(color)
                self.tab.spoit_active = False
                self.tab.view.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.is_drawing = True
                self.last_point = pos
                self.tab.erase_at(self.last_point, self.last_point)

    def mouseMoveEvent(self, event):
        if self.is_drawing and not self.tab.spoit_active:
            pos = event.scenePos()
            self.tab.erase_at(self.last_point, pos)
            self.last_point = pos

    def mouseReleaseEvent(self, event):
        self.is_drawing = False


class TransparencyTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        self.original_np = None # original RGBA array
        self.eraser_mask_qimage = None # QImage to store manual erasures
        self.current_display_qimage = None
        
        self.target_color = np.array([0, 0, 0], dtype=np.uint8)
        self.threshold = 0
        self.spoit_active = False
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.btn_load = QPushButton("Load Image")
        self.btn_load.clicked.connect(self.load_image)
        toolbar_layout.addWidget(self.btn_load)
        
        self.btn_save = QPushButton("Save Image")
        self.btn_save.clicked.connect(self.save_image)
        self.btn_save.setEnabled(False)
        toolbar_layout.addWidget(self.btn_save)

        self.btn_clear = QPushButton("Clear Output/Reset")
        self.btn_clear.clicked.connect(self.clear_image)
        self.btn_clear.setEnabled(False)
        toolbar_layout.addWidget(self.btn_clear)
        
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # Controls
        controls_group = QGroupBox("Transparency Settings")
        controls_layout = QHBoxLayout()
        
        # Tools
        tools_layout = QVBoxLayout()
        self.btn_spoit = QPushButton("Spoit (Pick Color)")
        self.btn_spoit.clicked.connect(self.activate_spoit)
        tools_layout.addWidget(self.btn_spoit)
        controls_layout.addLayout(tools_layout)

        # Sliders and Pickers
        sliders_layout = QFormLayout()
        
        # Color indicator
        self.color_indicator = QLabel()
        self.color_indicator.setFixedSize(30, 30)
        self.color_indicator.setStyleSheet("background-color: rgb(0, 0, 0); border: 1px solid black;")
        
        color_btn_layout = QHBoxLayout()
        color_btn_layout.addWidget(self.color_indicator)
        color_btn_layout.addStretch()
        sliders_layout.addRow("Target Color:", color_btn_layout)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 255)
        self.threshold_slider.setValue(0)
        self.threshold_slider.valueChanged.connect(self.on_threshold_changed)
        sliders_layout.addRow("Threshold:", self.threshold_slider)

        self.brush_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_size_slider.setRange(1, 100)
        self.brush_size_slider.setValue(20)
        sliders_layout.addRow("Eraser Brush Size:", self.brush_size_slider)
        
        controls_layout.addLayout(sliders_layout)
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Image View
        self.view = ResizableGraphicsView()
        self.scene = ImageScene(self)
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

    def activate_spoit(self):
        self.spoit_active = True
        self.view.setCursor(Qt.CursorShape.CrossCursor)

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if file_path:
            try:
                # Load with PIL and convert to RGBA
                img = Image.open(file_path).convert("RGBA")
                self.original_np = np.array(img) # Shape: (H, W, 4)
                
                h, w = self.original_np.shape[:2]
                
                # Reset eraser mask (completely transparent initially)
                self.eraser_mask_qimage = QImage(w, h, QImage.Format.Format_ARGB32)
                self.eraser_mask_qimage.fill(Qt.GlobalColor.transparent)
                
                self.scene.setSceneRect(0, 0, w, h)
                self.btn_save.setEnabled(True)
                self.btn_clear.setEnabled(True)
                self.threshold_slider.setValue(0)
                self.spoit_active = False
                self.view.setCursor(Qt.CursorShape.ArrowCursor)
                
                self.update_display()
                self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load image: {e}")

    def clear_image(self):
        self.original_np = None
        self.eraser_mask_qimage = None
        self.current_display_qimage = None
        self.pixmap_item.setPixmap(QPixmap())
        self.btn_save.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.scene.setSceneRect(0, 0, 0, 0)
        self.color_indicator.setStyleSheet("background-color: rgb(0, 0, 0); border: 1px solid black;")

    def set_target_color(self, color_np):
        self.target_color = color_np
        self.color_indicator.setStyleSheet(f"background-color: rgb({color_np[0]}, {color_np[1]}, {color_np[2]}); border: 1px solid black;")
        self.update_display()

    def on_threshold_changed(self, value):
        self.threshold = value
        self.update_display()

    def erase_at(self, p1, p2):
        if self.eraser_mask_qimage is None or self.current_display_qimage is None:
            return
            
        # Draw on eraser mask (opaque black where we want to erase)
        painter1 = QPainter(self.eraser_mask_qimage)
        pen = QPen(QColor(0, 0, 0, 255))
        pen.setWidth(self.brush_size_slider.value())
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter1.setPen(pen)
        painter1.drawLine(p1, p2)
        painter1.end()
        
        # Erase directly on display image for instant feedback using DestinationOut
        painter2 = QPainter(self.current_display_qimage)
        pen2 = QPen(QColor(0, 0, 0, 255)) # Color doesn't matter for DestinationOut, only alpha
        pen2.setWidth(self.brush_size_slider.value())
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter2.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        painter2.setPen(pen2)
        painter2.drawLine(p1, p2)
        painter2.end()
        
        self.pixmap_item.setPixmap(QPixmap.fromImage(self.current_display_qimage))

    def update_display(self):
        if self.original_np is None:
            return
            
        current_np = self.original_np.copy()
        
        if self.threshold > 0:
            diff = np.abs(current_np[:, :, :3].astype(np.int16) - self.target_color.astype(np.int16))
            dist = np.max(diff, axis=2)
            transparent_mask = dist <= self.threshold
            current_np[transparent_mask, 3] = 0
        else:
            diff = np.abs(current_np[:, :, :3].astype(np.int16) - self.target_color.astype(np.int16))
            dist = np.max(diff, axis=2)
            transparent_mask = dist == 0
            current_np[transparent_mask, 3] = 0

        # Create QImage from current_np
        h, w, ch = current_np.shape
        bytes_per_line = ch * w
        
        # We must keep a reference to current_np so the memory is not garbage collected
        # while QImage is using it. So we do a .copy() on the QImage to be completely safe.
        qimg = QImage(current_np.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
        self.current_display_qimage = qimg.copy()
            
        # Apply eraser mask
        if self.eraser_mask_qimage is not None:
            painter = QPainter(self.current_display_qimage)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            painter.drawImage(0, 0, self.eraser_mask_qimage)
            painter.end()
            
        self.pixmap_item.setPixmap(QPixmap.fromImage(self.current_display_qimage))

    def save_image(self):
        if self.current_display_qimage is None:
            return
            
        base_name = self.main_window.override_name_input.text().strip()
        start_index = self.main_window.start_index_input.value()
        default_name = f"{base_name}_{start_index}.png" if base_name else "transparent_image.png"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Image", default_name, "PNG Images (*.png)")
        if file_path:
            self.current_display_qimage.save(file_path, "PNG")
            QMessageBox.information(self, "Success", f"Saved to {file_path}")
