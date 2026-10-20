import os
from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                             QFileDialog, QGroupBox, QMessageBox, QGraphicsRectItem,
                             QGraphicsItem, QFormLayout, QComboBox, QSpinBox, QCheckBox)
from PyQt6.QtCore import Qt, QRectF, QRect
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush

from workers import CropWorkerThread
from components import ZoomableGraphicsView

# (label, (w, h)); None = free, "original" = current image's aspect ratio
RATIO_PRESETS = [
    ("Free", None),
    ("Original", "original"),
    ("1:1", (1, 1)),
    ("4:3", (4, 3)),
    ("3:4", (3, 4)),
    ("3:2", (3, 2)),
    ("2:3", (2, 3)),
    ("16:9", (16, 9)),
    ("9:16", (9, 16)),
    ("4:5", (4, 5)),
    ("5:4", (5, 4)),
    ("21:9", (21, 9)),
]


def fit_ratio(w, h, ratio, max_w, max_h):
    """Grow (w, h) to the given ratio along the larger side, then shrink to fit max_w x max_h."""
    if h <= 0 or w / h > ratio:
        h = w / ratio
    else:
        w = h * ratio
    if w > max_w:
        w = max_w
        h = w / ratio
    if h > max_h:
        h = max_h
        w = h * ratio
    return w, h


def anchored_ratio_rect(ax, ay, px, py, ratio, bounds):
    """Ratio-locked rect spanning from anchor (ax, ay) toward point (px, py), clamped to bounds."""
    sx = 1 if px >= ax else -1
    sy = 1 if py >= ay else -1
    max_w = (bounds.right() - ax) if sx > 0 else (ax - bounds.left())
    max_h = (bounds.bottom() - ay) if sy > 0 else (ay - bounds.top())
    w, h = fit_ratio(abs(px - ax), abs(py - ay), ratio, max_w, max_h)
    x = ax if sx > 0 else ax - w
    y = ay if sy > 0 else ay - h
    return QRectF(x, y, w, h)


class ResizableCropRect(QGraphicsRectItem):
    def __init__(self, scene):
        super().__init__()
        self.scene_ref = scene
        self.setAcceptHoverEvents(True)
        
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(255, 0, 0, 50)))
        self.setZValue(1)

        self.active_handle = None
        self.dragging_center = False
        self.drag_offset = None

    def handle_size(self):
        # Keep handles ~10 screen px regardless of zoom
        views = self.scene_ref.views()
        scale = views[0].transform().m11() if views else 1.0
        return 10 / scale if scale > 0 else 10

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
        s = self.handle_size()
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
            
        s = self.handle_size()
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        pen = QPen(QColor(0, 0, 0))
        pen.setCosmetic(True)
        painter.setPen(pen)
        
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
            
    def ratio_resize(self, pos, ratio):
        r = self.rect()
        b = self.scene_ref.sceneRect()
        h = self.active_handle
        if len(h) == 2:
            # Corner: opposite corner stays fixed
            ax = r.right() if 'l' in h else r.left()
            ay = r.bottom() if 't' in h else r.top()
            return anchored_ratio_rect(ax, ay, pos.x(), pos.y(), ratio, b)
        if h in ('t', 'b'):
            # Edge: opposite edge stays fixed, width follows centered
            ay = r.bottom() if h == 't' else r.top()
            cx = r.center().x()
            new_h = max(0, (ay - pos.y()) if h == 't' else (pos.y() - ay))
            max_h = (ay - b.top()) if h == 't' else (b.bottom() - ay)
            max_w = 2 * min(cx - b.left(), b.right() - cx)
            w, new_h = fit_ratio(0, new_h, ratio, max_w, max_h)
            y = ay - new_h if h == 't' else ay
            return QRectF(cx - w / 2, y, w, new_h)
        ax = r.right() if h == 'l' else r.left()
        cy = r.center().y()
        new_w = max(0, (ax - pos.x()) if h == 'l' else (pos.x() - ax))
        max_w = (ax - b.left()) if h == 'l' else (b.right() - ax)
        max_h = 2 * min(cy - b.top(), b.bottom() - cy)
        new_w, hh = fit_ratio(new_w, 0, ratio, max_w, max_h)
        x = ax - new_w if h == 'l' else ax
        return QRectF(x, cy - hh / 2, new_w, hh)

    def mouseMoveEvent(self, event):
        ratio = self.scene_ref.tab.locked_ratio()
        if self.active_handle and ratio:
            self.setRect(self.ratio_resize(event.pos(), ratio))
            self.scene_ref.update_current_rect()
            event.accept()
        elif self.active_handle:
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
        was_editing = self.active_handle or self.dragging_center
        self.active_handle = None
        self.dragging_center = False
        if was_editing:
            self.scene_ref.snap_rect()
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
            ratio = self.tab.locked_ratio()
            if ratio:
                self.rect_item.setRect(anchored_ratio_rect(
                    self.start_pos.x(), self.start_pos.y(),
                    current_pos.x(), current_pos.y(), ratio, self.sceneRect()))
            else:
                # Constrain within scene bounds
                x1 = max(0, min(self.start_pos.x(), current_pos.x()))
                y1 = max(0, min(self.start_pos.y(), current_pos.y()))
                x2 = min(self.width(), max(self.start_pos.x(), current_pos.x()))
                y2 = min(self.height(), max(self.start_pos.y(), current_pos.y()))

                self.rect_item.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))
            self.tab.sync_size_inputs()
            
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
            self.snap_rect()
            self.update_current_rect()
        super().mouseReleaseEvent(event)

    def snap_rect(self):
        """Round the crop rect to whole pixels so it matches the exported size exactly."""
        r = self.rect_item.rect()
        if r.width() < 1 or r.height() < 1:
            return
        self.tab.set_crop_rect(r.center().x(), r.center().y(), r.width(), r.height())

    def update_current_rect(self):
        rect = self.rect_item.rect()
        if rect.width() >= 1 and rect.height() >= 1:
            self.current_rect = rect
        else:
            self.rect_item.hide()
            self.current_rect = None
        self.tab.sync_size_inputs()

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
        inst_label = QLabel("Drag a rectangle over the image to define the crop area, or pick a ratio / enter a size below. All dragged files will be cropped to this exact position and size.")
        inst_label.setWordWrap(True)
        inst_layout.addWidget(inst_label)
        instructions_group.setLayout(inst_layout)
        layout.addWidget(instructions_group)

        # Crop size settings
        settings_group = QGroupBox("Crop Size")
        form = QFormLayout()

        self.ratio_combo = QComboBox()
        for label, value in RATIO_PRESETS:
            self.ratio_combo.addItem(label, value)
        self.ratio_combo.currentIndexChanged.connect(self.on_ratio_changed)
        form.addRow("Ratio:", self.ratio_combo)

        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        for spin in (self.x_spin, self.y_spin):
            spin.setRange(0, 32767)
            spin.setSuffix(" px")
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self.on_offset_changed)
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(QLabel("X"))
        offset_layout.addWidget(self.x_spin)
        offset_layout.addWidget(QLabel("Y"))
        offset_layout.addWidget(self.y_spin)
        form.addRow("Offset:", offset_layout)

        self.center_check = QCheckBox("Center (per image on export)")
        self.center_check.toggled.connect(self.on_center_toggled)
        form.addRow("", self.center_check)

        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin, dim in ((self.width_spin, "width"), (self.height_spin, "height")):
            spin.setRange(1, 32768)
            spin.setSuffix(" px")
            # Apply on Enter / focus out / arrows, not on every keystroke
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(lambda v, d=dim: self.on_size_changed(d, v))
        dims_layout = QHBoxLayout()
        dims_layout.addWidget(QLabel("W"))
        dims_layout.addWidget(self.width_spin)
        dims_layout.addWidget(QLabel("H"))
        dims_layout.addWidget(self.height_spin)
        form.addRow("Size:", dims_layout)

        self.lock_check = QCheckBox("Lock ratio")
        self.lock_check.toggled.connect(self.on_lock_toggled)
        form.addRow("", self.lock_check)

        settings_group.setLayout(form)
        layout.addWidget(settings_group)
        layout.addStretch()

        # Ratio captured when "Lock ratio" is checked while the ratio is "Free"
        self.custom_ratio = None

        # Preview panel (shown in the main window): navigation + image view
        self.preview_widget = QWidget()
        preview_layout = QVBoxLayout(self.preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

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
        
        preview_layout.addLayout(nav_layout)

        # Image View
        self.view = ZoomableGraphicsView()
        self.view.setMouseTracking(True)
        self.scene = CropScene(self)
        self.view.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        # Checkerboard background
        bg_pixmap = self.create_checkerboard_pattern()
        self.view.setBackgroundBrush(QBrush(bg_pixmap))
        preview_layout.addWidget(self.view)

    def image_size(self):
        if self.original_img is None or self.original_img.isNull():
            return None
        return self.original_img.width(), self.original_img.height()

    def current_crop_rect(self):
        return self.scene.current_rect if self.scene.rect_item.isVisible() else None

    def locked_ratio(self):
        """Width / height ratio the crop rect must keep, or None when free."""
        if not self.lock_check.isChecked():
            return None
        value = self.ratio_combo.currentData()
        if value is None:
            return self.custom_ratio
        if value == "original":
            size = self.image_size()
            return size[0] / size[1] if size else None
        return value[0] / value[1]

    def clamped_rect(self, cx, cy, w, h, top_left=None):
        """Whole-pixel rect of size w x h centered near (cx, cy) (or at top_left), kept inside the image."""
        img_w, img_h = self.image_size()
        w = min(max(1, int(round(w))), img_w)
        h = min(max(1, int(round(h))), img_h)
        if self.center_check.isChecked():
            # Same formula the export worker uses per image
            x, y = (img_w - w) // 2, (img_h - h) // 2
        else:
            x, y = top_left if top_left else (cx - w / 2, cy - h / 2)
        x = max(0, min(round(x), img_w - w))
        y = max(0, min(round(y), img_h - h))
        return QRectF(x, y, w, h)

    def set_crop_rect(self, cx, cy, w, h, drive="width", top_left=None):
        """Place a w x h crop rect around (cx, cy) or at top_left; when locked, the non-driving side follows the ratio."""
        ratio = self.locked_ratio()
        if ratio:
            img_w, img_h = self.image_size()
            w, h = fit_ratio(w, h, ratio, img_w, img_h)
            if drive == "width" and round(w) / ratio <= img_h:
                w = max(1, round(w))
                h = w / ratio
            elif round(h) * ratio <= img_w:
                h = max(1, round(h))
                w = h * ratio
        self.scene.rect_item.setRect(self.clamped_rect(cx, cy, w, h, top_left))
        self.scene.rect_item.show()
        self.scene.update_current_rect()

    def sync_size_inputs(self):
        rect = self.scene.rect_item.rect() if self.scene.rect_item.isVisible() else None
        if rect is None or rect.width() < 1 or rect.height() < 1:
            return
        for spin, value in ((self.x_spin, rect.x()), (self.y_spin, rect.y()),
                            (self.width_spin, max(1, rect.width())), (self.height_spin, max(1, rect.height()))):
            spin.blockSignals(True)
            spin.setValue(round(value))
            spin.blockSignals(False)

    def on_ratio_changed(self, _index):
        is_free = self.ratio_combo.currentData() is None
        self.lock_check.blockSignals(True)
        self.lock_check.setChecked(not is_free)
        self.lock_check.blockSignals(False)
        self.custom_ratio = None
        if not is_free:
            self.apply_ratio()

    def on_lock_toggled(self, checked):
        if checked:
            if self.ratio_combo.currentData() is None:
                rect = self.current_crop_rect()
                size = self.image_size()
                if rect is not None:
                    self.custom_ratio = rect.width() / rect.height()
                elif size:
                    self.custom_ratio = size[0] / size[1]
                else:
                    self.custom_ratio = self.width_spin.value() / self.height_spin.value()
        else:
            # Unlocking makes the ratio free again
            self.ratio_combo.blockSignals(True)
            self.ratio_combo.setCurrentIndex(0)
            self.ratio_combo.blockSignals(False)
            self.custom_ratio = None

    def apply_ratio(self):
        """Reshape the crop rect to the locked ratio, keeping its center and width where possible."""
        size = self.image_size()
        ratio = self.locked_ratio()
        if not size or not ratio:
            return
        img_w, img_h = size
        rect = self.current_crop_rect()
        if rect is not None:
            cx, cy = rect.center().x(), rect.center().y()
            w = rect.width()
        else:
            # No selection yet: largest centered rect with this ratio
            cx, cy = img_w / 2, img_h / 2
            w = img_w
        self.set_crop_rect(cx, cy, w, 0)

    def on_size_changed(self, dim, _value):
        size = self.image_size()
        if not size:
            return
        ratio = self.locked_ratio()
        w, h = self.width_spin.value(), self.height_spin.value()
        if ratio:
            # Drop the other side so the edited one drives the ratio fit
            if dim == "width":
                h = 0
            else:
                w = 0
        rect = self.current_crop_rect()
        if rect is not None:
            # Keep the top-left corner (the X/Y offset) fixed while resizing
            self.set_crop_rect(0, 0, w, h, drive=dim, top_left=(rect.x(), rect.y()))
        else:
            self.set_crop_rect(size[0] / 2, size[1] / 2, w, h, drive=dim)

    def on_center_toggled(self, checked):
        self.x_spin.setEnabled(not checked)
        self.y_spin.setEnabled(not checked)
        rect = self.current_crop_rect()
        if checked and rect is not None:
            self.set_crop_rect(0, 0, rect.width(), rect.height())

    def on_offset_changed(self, _value):
        size = self.image_size()
        if not size:
            return
        x, y = self.x_spin.value(), self.y_spin.value()
        rect = self.current_crop_rect()
        if rect is not None:
            w, h = rect.width(), rect.height()
        else:
            # No selection yet: take the remaining area from the offset to the image edge
            w, h = size[0] - x, size[1] - y
            ratio = self.locked_ratio()
            if ratio:
                w, h = fit_ratio(w, 0, ratio, w, h)
        self.set_crop_rect(0, 0, w, h, top_left=(x, y))

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
                for spin, limit in ((self.width_spin, w), (self.height_spin, h),
                                    (self.x_spin, w - 1), (self.y_spin, h - 1)):
                    spin.blockSignals(True)
                    spin.setMaximum(limit)
                    spin.blockSignals(False)
                rect = self.current_crop_rect()
                if self.center_check.isChecked() and rect is not None:
                    self.set_crop_rect(0, 0, rect.width(), rect.height())
                
                self.main_window.set_export_enabled(True)
                
                self.view.fit_view()
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
        x = round(rect.x())
        y = round(rect.y())
        w = round(rect.width())
        h = round(rect.height())
        crop_rect = (x, y, w, h)

        override_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()

        self.crop_thread = CropWorkerThread(valid_files, output_dir, crop_rect, override_name, start_index,
                                            center=self.center_check.isChecked())
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
