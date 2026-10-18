from PyQt6.QtWidgets import QLabel, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QImage, QPixmap, QPainter, QColor, QBrush


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
    filesDropped = pyqtSignal(list)

    def __init__(self, text="Drag and Drop multiple files here", file_types=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.file_types = file_types or []
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
