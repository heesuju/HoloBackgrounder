import os
from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QFileDialog, QGroupBox, QMessageBox, QGraphicsRectItem,
                             QGraphicsItem)
from PyQt6.QtCore import Qt, QRectF, QRect
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush

from workers import CropWorkerThread

class ResizableGraphicsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene() and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

class ResizableCropRect(QGraphicsRectItem):
    def __init__(self, scene):
        super().__init__()
        self.scene_ref = scene
        self.setAcceptHoverEvents(True)
        
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(255, 0, 0, 50)))
        self.setZValue(1)
        
        self.handle_size = 10
        self.active_handle = None
        self.dragging_center = False
        self.drag_offset = None

    def hoverMoveEvent(self, event):
        handle = self.get_handle_at(event.pos())
        if handle in ('tl', 'br'):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ('tr', 'bl'):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle in ('t', 'b'):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in ('l', 'r'):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif self.rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)
        
    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def get_handle_at(self, pos):
        r = self.rect()
        s = self.handle_size
        handles = {
            'tl': QRectF(r.left() - s/2, r.top() - s/2, s, s),
            't':  QRectF(r.center().x() - s/2, r.top() - s/2, s, s),
            'tr': QRectF(r.right() - s/2, r.top() - s/2, s, s),
            'r':  QRectF(r.right() - s/2, r.center().y() - s/2, s, s),
            'br': QRectF(r.right() - s/2, r.bottom() - s/2, s, s),
            'b':  QRectF(r.center().x() - s/2, r.bottom() - s/2, s, s),
            'bl': QRectF(r.left() - s/2, r.bottom() - s/2, s, s),
            'l':  QRectF(r.left() - s/2, r.center().y() - s/2, s, s),
        }
        for k, v in handles.items():
            if v.contains(pos):
                return k
        return None

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        r = self.rect()
        if r.isEmpty():
            return
            
        s = self.handle_size
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(0, 0, 0)))
        
        handles = [
            QRectF(r.left() - s/2, r.top() - s/2, s, s),
            QRectF(r.center().x() - s/2, r.top() - s/2, s, s),
            QRectF(r.right() - s/2, r.top() - s/2, s, s),
            QRectF(r.right() - s/2, r.center().y() - s/2, s, s),
            QRectF(r.right() - s/2, r.bottom() - s/2, s, s),
            QRectF(r.center().x() - s/2, r.bottom() - s/2, s, s),
            QRectF(r.left() - s/2, r.bottom() - s/2, s, s),
            QRectF(r.left() - s/2, r.center().y() - s/2, s, s),
        ]
        for hr in handles:
            painter.drawRect(hr)

    def mousePressEvent(self, event):
        self.active_handle = self.get_handle_at(event.pos())
        if self.active_handle:
            event.accept()
        elif self.rect().contains(event.pos()):
            self.dragging_center = True
            self.drag_offset = event.pos() - self.rect().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        if self.active_handle:
            pos = event.pos()
            r = self.rect()
            
            x1, y1 = r.left(), r.top()
            x2, y2 = r.right(), r.bottom()
            
            if 't' in self.active_handle: y1 = pos.y()
            if 'b' in self.active_handle: y2 = pos.y()
            if 'l' in self.active_handle: x1 = pos.x()
            if 'r' in self.active_handle: x2 = pos.x()
            
            scene_rect = self.scene_ref.sceneRect()
            x1 = max(scene_rect.left(), min(x1, scene_rect.right()))
            y1 = max(scene_rect.top(), min(y1, scene_rect.bottom()))
            x2 = max(scene_rect.left(), min(x2, scene_rect.right()))
            y2 = max(scene_rect.top(), min(y2, scene_rect.bottom()))
            
            if x2 < x1:
                if 'l' in self.active_handle: x1 = x2
                elif 'r' in self.active_handle: x2 = x1
            if y2 < y1:
                if 't' in self.active_handle: y1 = y2
                elif 'b' in self.active_handle: y2 = y1
            
            self.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))
            self.scene_ref.update_current_rect()
            event.accept()
            
        elif self.dragging_center:
            pos = event.pos()
            r = self.rect()
            new_top_left = pos - self.drag_offset
            
            scene_rect = self.scene_ref.sceneRect()
            x = max(scene_rect.left(), min(new_top_left.x(), scene_rect.right() - r.width()))
            y = max(scene_rect.top(), min(new_top_left.y(), scene_rect.bottom() - r.height()))
            
            self.setRect(QRectF(x, y, r.width(), r.height()))
            self.scene_ref.update_current_rect()
            event.accept()
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        self.active_handle = None
        self.dragging_center = False
        self.scene_ref.update_current_rect()
        super().mouseReleaseEvent(event)

class CropScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab = parent
        self.is_dragging = False
        self.start_pos = None
        
        self.rect_item = ResizableCropRect(self)
        self.addItem(self.rect_item)
        self.rect_item.hide()
        self.current_rect = None
        
        self.loupe_item = QGraphicsPixmapItem()
        self.loupe_item.setZValue(2)
        # Prevent the loupe from shrinking when the view scales down large images
        self.loupe_item.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.addItem(self.loupe_item)
        self.loupe_item.hide()

    def mousePressEvent(self, event):
        if self.tab.original_img is None:
            return

        super().mousePressEvent(event)
        if self.rect_item.active_handle or self.rect_item.dragging_center:
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
            
        if self.tab.original_img:
            pos = event.scenePos()
            x = int(pos.x())
            y = int(pos.y())
            w = self.tab.original_img.width()
            h = self.tab.original_img.height()
            
            if 0 <= x < w and 0 <= y < h:
                # 20x20 pixel area around cursor
                crop_rect = QRect(x - 10, y - 10, 20, 20)
                sub_img = self.tab.original_img.copy(crop_rect)
                
                loupe_pix = QPixmap.fromImage(sub_img).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
                
                painter = QPainter(loupe_pix)
                
                # Draw border (keep green or use red? let's make border black/white or keep green)
                painter.setPen(QPen(Qt.GlobalColor.green, 1))
                painter.drawRect(0, 0, 99, 99)
                
                # Draw Red Crosshair
                painter.setPen(QPen(Qt.GlobalColor.red, 1))
                # Center pixel is roughly at 50,50
                painter.drawLine(50, 40, 50, 60)
                painter.drawLine(40, 50, 60, 50)
                
                painter.end()
                
                self.loupe_item.setPixmap(loupe_pix)
                
                # Position loupe (offset so it doesn't block cursor)
                # Map offset to scene coordinates if needed, but since it ignores transformations,
                # we just need to set its scene pos.
                # However, with ItemIgnoresTransformations, setPos is the anchor point in scene coordinates.
                # Let's map cursor position to view coordinates, add offset, and map back to scene to position it.
                view = self.views()[0]
                view_pos = view.mapFromScene(pos)
                view_pos.setX(view_pos.x() + 15)
                view_pos.setY(view_pos.y() + 15)
                
                # Check view boundaries
                if view_pos.x() + 100 > view.viewport().width():
                    view_pos.setX(view_pos.x() - 130)
                if view_pos.y() + 100 > view.viewport().height():
                    view_pos.setY(view_pos.y() - 130)
                    
                scene_pos = view.mapToScene(view_pos)
                self.loupe_item.setPos(scene_pos)
                self.loupe_item.show()
            else:
                self.loupe_item.hide()
                
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.update_current_rect()
        super().mouseReleaseEvent(event)

    def update_current_rect(self):
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
