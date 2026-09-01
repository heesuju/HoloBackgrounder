import os
from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QFileDialog, QGroupBox, QMessageBox, QGraphicsRectItem)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush

from workers import CropWorkerThread

class ResizableGraphicsView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene() and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

class CropScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab = parent
        self.is_dragging = False
        self.start_pos = None
        
        self.rect_item = QGraphicsRectItem()
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.rect_item.setPen(pen)
        self.rect_item.setBrush(QBrush(QColor(255, 0, 0, 50))) # semi-transparent red
        self.rect_item.setZValue(1)
        self.addItem(self.rect_item)
        self.rect_item.hide()
        self.current_rect = None

    def mousePressEvent(self, event):
        if self.tab.original_img is None:
            return
        self.is_dragging = True
        self.start_pos = event.scenePos()
        self.rect_item.setRect(QRectF(self.start_pos, self.start_pos))
        self.rect_item.show()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            current_pos = event.scenePos()
            # Constrain within scene bounds
            x1 = max(0, min(self.start_pos.x(), current_pos.x()))
            y1 = max(0, min(self.start_pos.y(), current_pos.y()))
            x2 = min(self.width(), max(self.start_pos.x(), current_pos.x()))
            y2 = min(self.height(), max(self.start_pos.y(), current_pos.y()))
            
            self.rect_item.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            rect = self.rect_item.rect()
            if rect.width() > 0 and rect.height() > 0:
                self.current_rect = rect
            else:
                self.rect_item.hide()
                self.current_rect = None

class CropTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        self.original_img = None
        self.crop_thread = None
        self.valid_files = []
        self.current_preview_index = 0
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Instructions
        instructions_group = QGroupBox("Instructions")
        inst_layout = QVBoxLayout()
        inst_label = QLabel("Drag a rectangle over the image to define the crop area. All dragged files will be cropped to this exact position and size.")
        inst_label.setWordWrap(True)
        inst_layout.addWidget(inst_label)
        
        # Navigation
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("< Previous")
        self.prev_btn.clicked.connect(self.prev_image)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn)
        
        self.preview_label = QLabel("Preview 0 / 0")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.preview_label)
        
        self.next_btn = QPushButton("Next >")
        self.next_btn.clicked.connect(self.next_image)
        self.next_btn.setEnabled(False)
        nav_layout.addWidget(self.next_btn)
        
        inst_layout.addLayout(nav_layout)
        instructions_group.setLayout(inst_layout)
        layout.addWidget(instructions_group)

        # Image View
        self.view = ResizableGraphicsView()
        self.scene = CropScene(self)
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
        self.valid_files = [f for f in self.main_window.current_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
        
        if self.valid_files:
            self.current_preview_index = 0
            self.scene.rect_item.hide()
            self.scene.current_rect = None
            self.update_preview()
        else:
            self.clear_image()
            
    def update_preview(self):
        if not self.valid_files:
            self.clear_image()
            return
            
        self.preview_label.setText(f"Preview {self.current_preview_index + 1} / {len(self.valid_files)}")
        self.prev_btn.setEnabled(self.current_preview_index > 0)
        self.next_btn.setEnabled(self.current_preview_index < len(self.valid_files) - 1)
        
        self.load_image_from_path(self.valid_files[self.current_preview_index])
        
    def prev_image(self):
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            self.update_preview()
            
    def next_image(self):
        if self.current_preview_index < len(self.valid_files) - 1:
            self.current_preview_index += 1
            self.update_preview()

    def load_image_from_path(self, file_path):
        if file_path:
            try:
                self.original_img = QImage(file_path)
                if self.original_img.isNull():
                    raise ValueError("Failed to load image via QImage.")
                
                w = self.original_img.width()
                h = self.original_img.height()
                
                self.scene.setSceneRect(0, 0, w, h)
                self.pixmap_item.setPixmap(QPixmap.fromImage(self.original_img))
                
                self.main_window.set_export_enabled(True)
                
                self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load preview image: {e}")

    def clear_image(self):
        self.original_img = None
        self.pixmap_item.setPixmap(QPixmap())
        self.scene.rect_item.hide()
        self.scene.current_rect = None
        self.main_window.set_export_enabled(False)
        self.scene.setSceneRect(0, 0, 0, 0)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.preview_label.setText("Preview 0 / 0")

    def export(self):
        if self.scene.current_rect is None:
            QMessageBox.warning(self, "No Crop Area", "Please drag a rectangle on the image to define the crop area before exporting.")
            return

        valid_files = [f for f in self.main_window.current_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
        if not valid_files:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        rect = self.scene.current_rect
        x = int(rect.x())
        y = int(rect.y())
        w = int(rect.width())
        h = int(rect.height())
        crop_rect = (x, y, w, h)

        override_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()

        self.crop_thread = CropWorkerThread(valid_files, output_dir, crop_rect, override_name, start_index)
        self.crop_thread.finished.connect(self.on_crop_finished)
        self.crop_thread.progress.connect(self.update_crop_status)
        
        self.main_window.set_export_enabled(False)
        self.main_window.set_status("Cropping images...")
        self.crop_thread.start()

    def update_crop_status(self, message):
        self.main_window.set_status(message)

    def on_crop_finished(self, success, message):
        self.main_window.set_export_enabled(True)
        self.main_window.set_status(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)
