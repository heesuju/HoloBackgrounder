from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

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
