import os
from PyQt6.QtWidgets import QLabel, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QImage, QPixmap, QPainter, QColor, QBrush, QPen


def checkerboard_pixmap(size=20, light=QColor(200, 200, 200), dark=QColor(150, 150, 150)):
    img = QImage(size * 2, size * 2, QImage.Format.Format_RGB32)
    painter = QPainter(img)
    painter.fillRect(0, 0, size * 2, size * 2, dark)
    painter.fillRect(0, 0, size, size, light)
    painter.fillRect(size, size, size, size, light)
    painter.end()
    return QPixmap.fromImage(img)


class ZoomableGraphicsView(QGraphicsView):
    """Preview view that zooms with the mouse wheel but never below fit-to-view.
    Pans with the middle mouse button (and the left button when pan_with_left
    is set, for views with no left-click tools). Middle double-click re-fits."""

    MAX_ZOOM = 32.0   # largest on-screen size of one scene pixel
    ZOOM_STEP = 1.25

    def __init__(self, parent=None, pan_with_left=False):
        super().__init__(parent)
        self.pan_with_left = pan_with_left
        self._fit = True
        self._pan_pos = None
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def has_content(self):
        return self.scene() is not None and not self.scene().sceneRect().isEmpty()

    def fit_scale(self):
        r = self.scene().sceneRect()
        vp = self.viewport().rect()
        return min(vp.width() / r.width(), vp.height() / r.height())

    def fit_view(self):
        """Reset zoom so the whole scene fits; the view keeps fitting on resize until zoomed."""
        self._fit = True
        self.resetTransform()
        if not self.has_content():
            return
        s = self.fit_scale()
        if s > 0:
            self.scale(s, s)
        self.centerOn(self.scene().sceneRect().center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.has_content() and (self._fit or self.transform().m11() < self.fit_scale()):
            self.fit_view()

    def showEvent(self, event):
        super().showEvent(event)
        if self._fit:
            self.fit_view()

    def wheelEvent(self, event):
        if not self.has_content():
            return
        steps = event.angleDelta().y() / 120
        if steps == 0:
            return
        fit = self.fit_scale()
        cur = self.transform().m11()
        target = cur * self.ZOOM_STEP ** steps
        if target <= fit * 1.001:
            self.fit_view()
        else:
            target = min(target, max(self.MAX_ZOOM, fit))
            self._fit = False
            self.scale(target / cur, target / cur)
        event.accept()

    def _is_pan_button(self, button):
        return button == Qt.MouseButton.MiddleButton or (
            self.pan_with_left and button == Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event):
        if self._is_pan_button(event.button()):
            self._pan_pos = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_pos is not None:
            delta = event.position() - self._pan_pos
            self._pan_pos = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_pos is not None and self._is_pan_button(event.button()):
            self._pan_pos = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fit_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class FilePreview(ZoomableGraphicsView):
    """Fallback preview for tabs without their own: shows the first loadable image."""

    def __init__(self, parent=None):
        super().__init__(parent, pan_with_left=True)
        self.setBackgroundBrush(QBrush(checkerboard_pixmap()))
        self.setScene(QGraphicsScene(self))
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene().addItem(self.pixmap_item)

    def show_files(self, file_paths):
        for path in file_paths:
            img = QImage(path)
            if not img.isNull():
                self.pixmap_item.setPixmap(QPixmap.fromImage(img))
                self.scene().setSceneRect(0, 0, img.width(), img.height())
                self.fit_view()
                return
        self.pixmap_item.setPixmap(QPixmap())
        self.scene().setSceneRect(0, 0, 0, 0)
        self.fit_view()

class DragDropLabel(QLabel):
    fileDropped = pyqtSignal(str)

    def __init__(self, text="Drag and Drop file here\nor\nClick 'Browse' to select", file_types=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.file_types = file_types or ['.gif', '.webm']
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                padding: 20px;
                background-color: #f0f0f0;
                color: #555;
            }
            QLabel:hover {
                border-color: #55aaff;
                background-color: #e0f0ff;
            }
        """)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile().lower()
                if not self.file_types or any(file_path.endswith(ext) for ext in self.file_types):
                    event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if not self.file_types or any(file_path.lower().endswith(ext) for ext in self.file_types):
                self.fileDropped.emit(file_path)

class MultiDragDropLabel(QLabel):
    """Fixed-height drop area. Shows the prompt text when empty and a row of
    thumbnails of the selected files otherwise, without changing size.
    Clicking the area emits clicked; the x on a thumbnail emits removeRequested(index)."""

    filesDropped = pyqtSignal(list)
    clicked = pyqtSignal()
    removeRequested = pyqtSignal(int)

    HEIGHT = 130
    MAX_THUMBS = 24     # thumbnails are only loaded for the first files
    THUMB_GAP = 6
    CLOSE_SIZE = 18

    def __init__(self, text="Drag and Drop multiple files here", file_types=None, parent=None):
        super().__init__(parent)
        self.prompt_text = text
        self.setText(text)
        self.file_types = file_types or []
        self.files = []
        self.thumb_cache = {}   # path -> QPixmap, or None for files that aren't images
        self.close_rects = []   # (QRect, file index) of the x buttons, set while painting
        self.hover_close = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(1)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                padding: 8px;
                background-color: #f0f0f0;
                color: #555;
            }
            QLabel:hover {
                border-color: #55aaff;
                background-color: #e0f0ff;
            }
            QLabel[hasFiles="true"] {
                border: 2px solid #55cc55;
                background-color: #e0ffe0;
            }
        """)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checker = QBrush(checkerboard_pixmap(6, QColor(235, 235, 235), QColor(205, 205, 205)))

    def set_files(self, file_paths):
        self.files = list(file_paths)
        thumb_px = self.HEIGHT * 2
        cache = {}
        for path in self.files[:self.MAX_THUMBS]:
            if path in self.thumb_cache:
                cache[path] = self.thumb_cache[path]
                continue
            img = QImage(path)
            if img.isNull() and path.lower().endswith(('.mp4', '.webm', '.avi', '.mov', '.mkv', '.m4v', '.wmv')):
                try:
                    import cv2
                    cap = cv2.VideoCapture(path)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            h, w, ch = rgb.shape
                            img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                        cap.release()
                except Exception:
                    pass
            cache[path] = None if img.isNull() else QPixmap.fromImage(img.scaled(
                thumb_px, thumb_px, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        self.thumb_cache = cache
        self.hover_close = None
        self.setText("" if self.files else self.prompt_text)
        self._set_has_files(bool(self.files))

    def clear_files(self):
        self.set_files([])

    def _set_has_files(self, value):
        self.setProperty("hasFiles", value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        self.close_rects = []
        if not self.files:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        area = self.contentsRect()
        side = area.height()
        gap = self.THUMB_GAP
        fit = max(1, (area.width() + gap) // (side + gap))
        total = len(self.files)
        shown = min(total, fit, self.MAX_THUMBS)
        overflow = total - shown
        if overflow > 0 and shown == fit:
            shown -= 1          # last slot shows "+N"
            overflow += 1

        slots = shown + (1 if overflow > 0 else 0)
        x = area.left() + (area.width() - (slots * side + (slots - 1) * gap)) // 2
        y = area.top()
        for i in range(shown):
            box = QRect(x, y, side, side)
            pix = self.thumb_cache.get(self.files[i])
            painter.fillRect(box, self._checker)
            if pix is not None:
                scaled = pix.size().scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio)
                target = QRect(0, 0, scaled.width(), scaled.height())
                target.moveCenter(box.center())
                painter.drawPixmap(target, pix)
            else:
                ext = os.path.splitext(self.files[i])[1].upper().lstrip('.') or "FILE"
                painter.setPen(QColor(85, 85, 85))
                painter.drawText(box, Qt.AlignmentFlag.AlignCenter, ext)
            painter.setPen(QColor(170, 170, 170))
            painter.drawRect(box.adjusted(0, 0, -1, -1))
            self.draw_close_button(painter, box, i)
            x += side + gap
        if overflow > 0:
            box = QRect(x, y, side, side)
            painter.fillRect(box, QColor(0, 0, 0, 30))
            painter.setPen(QColor(60, 60, 60))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 4)
            painter.setFont(font)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, f"+{overflow}")
            painter.setFont(self.font())
        painter.end()

    def draw_close_button(self, painter, box, index):
        s = self.CLOSE_SIZE
        rect = QRect(box.right() - s - 2, box.top() + 2, s, s)
        self.close_rects.append((rect, index))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(220, 50, 50) if self.hover_close == index else QColor(0, 0, 0, 150))
        painter.drawEllipse(rect)
        pen = QPen(QColor(255, 255, 255), 2)
        painter.setPen(pen)
        m = 5
        painter.drawLine(rect.left() + m, rect.top() + m, rect.right() - m + 1, rect.bottom() - m + 1)
        painter.drawLine(rect.right() - m + 1, rect.top() + m, rect.left() + m, rect.bottom() - m + 1)
        painter.restore()

    def close_index_at(self, pos):
        for rect, index in self.close_rects:
            if rect.contains(pos):
                return index
        return None

    def mouseMoveEvent(self, event):
        index = self.close_index_at(event.position().toPoint())
        if index != self.hover_close:
            self.hover_close = index
            self.setToolTip("Remove" if index is not None else "")
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hover_close is not None:
            self.hover_close = None
            self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            index = self.close_index_at(event.position().toPoint())
            if index is not None:
                self.removeRequested.emit(index)
            else:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        valid_files = []
        for url in urls:
            file_path = url.toLocalFile()
            if not self.file_types or any(file_path.lower().endswith(ext) for ext in self.file_types):
                valid_files.append(file_path)
        if valid_files:
            self.filesDropped.emit(valid_files)
