import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QGroupBox, 
                             QFormLayout, QLineEdit, QSpinBox, QTabWidget, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QSplitter, QStackedWidget)
from PyQt6.QtCore import pyqtSignal, Qt

from components import MultiDragDropLabel, FilePreview
from tabs.gif_tab import GifTab
from tabs.split_tab import SplitTab
from tabs.rename_tab import RenameTab
from tabs.transparency_tab import TransparencyTab
from tabs.outline_tab import OutlineTab
from tabs.crop_tab import CropTab
from tabs.pdf_tab import PdfTab
from tabs.pixel_tab import PixelTab
from tabs.icon_tab import IconTab
from tabs.resize_tab import ResizeTab
from tabs.region_tab import RegionTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Processor")
        self.setGeometry(100, 100, 1400, 850)
        
        self.current_files = []

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left_widget = QWidget()
        main_layout = QVBoxLayout(left_widget)
        
        # 1. Global Input Section
        input_group = QGroupBox("Global Input Files (Drag & Drop)")
        input_layout = QVBoxLayout()
        
        self.drop_label = MultiDragDropLabel(text="Drag and Drop multiple files here\nor\nClick to browse")
        self.drop_label.filesDropped.connect(self.on_files_dropped)
        self.drop_label.clicked.connect(self.browse_files)
        self.drop_label.removeRequested.connect(self.remove_file)
        input_layout.addWidget(self.drop_label)

        self.file_path_label = QLabel("No files selected")
        self.file_path_label.setWordWrap(True)
        input_layout.addWidget(self.file_path_label)
        
        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)
        
        # 2. Common Output Section
        common_group = QGroupBox("Common Output Settings")
        common_layout = QFormLayout()

        self.override_name_input = QLineEdit("")
        self.override_name_input.setPlaceholderText("Optional: e.g., 'icon' or 'video_name'")
        self.override_name_input.setToolTip("Overrides the base filename for outputs.")
        common_layout.addRow("Override Base Name:", self.override_name_input)

        self.start_index_input = QSpinBox()
        self.start_index_input.setRange(0, 100000)
        self.start_index_input.setValue(1)
        self.start_index_input.setToolTip("Starting index for outputs (e.g. part_1, part_2).")
        common_layout.addRow("Start Index:", self.start_index_input)

        common_group.setLayout(common_layout)
        main_layout.addWidget(common_group)
        
        # 3. Tabs
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs)
        
        # 4. Global Export Section
        self.export_btn = QPushButton("Export")
        self.export_btn.setFixedHeight(45)
        self.export_btn.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.export_btn.clicked.connect(self.on_export_clicked)
        self.export_btn.setEnabled(False)
        main_layout.addWidget(self.export_btn)

        self.global_status_label = QLabel("")
        self.global_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.global_status_label)

        # 5. Preview (right side) - shows the current tab's preview widget
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        self.preview_stack = QStackedWidget()
        self.file_preview = FilePreview()
        self.preview_stack.addWidget(self.file_preview)
        preview_layout.addWidget(self.preview_stack)
        hint = QLabel("Scroll: zoom  ·  Middle-drag: pan  ·  Middle double-click: fit")
        hint.setStyleSheet("color: #777;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(hint)
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 840])

        self.init_tabs()
        self.on_tab_changed(self.tabs.currentIndex())

    def init_tabs(self):
        self.gif_tab = GifTab(self)
        self.split_tab = SplitTab(self)
        self.rename_tab = RenameTab(self)
        self.transparency_tab = TransparencyTab(self)
        self.outline_tab = OutlineTab(self)
        self.crop_tab = CropTab(self)
        self.pdf_tab = PdfTab(self)
        self.pixel_tab = PixelTab(self)
        self.icon_tab = IconTab(self)
        self.resize_tab = ResizeTab(self)
        self.region_tab = RegionTab(self)

        self.tabs.addTab(self.gif_tab, "GIF to MP4")
        self.tabs.addTab(self.split_tab, "Image Shape Splitter")
        self.tabs.addTab(self.rename_tab, "Batch Renamer")
        self.tabs.addTab(self.transparency_tab, "Color to Transparency")
        self.tabs.addTab(self.outline_tab, "Outline Generator")
        self.tabs.addTab(self.crop_tab, "Batch Crop")
        self.tabs.addTab(self.pdf_tab, "Images to PDF")
        self.tabs.addTab(self.pixel_tab, "픽셀화")
        self.tabs.addTab(self.icon_tab, "Icon Generator")
        self.tabs.addTab(self.resize_tab, "Lossless Resize")
        self.tabs.addTab(self.region_tab, "Region Swap")

        for i in range(self.tabs.count()):
            preview = getattr(self.tabs.widget(i), 'preview_widget', None)
            if preview is not None:
                self.preview_stack.addWidget(preview)
        
    def on_files_dropped(self, file_paths):
        import re, os
        def natural_keys(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
        
        self.current_files = sorted(file_paths, key=lambda x: natural_keys(os.path.basename(x)))
        self.file_path_label.setText(f"Selected: {len(self.current_files)} files")
        self.drop_label.set_files(self.current_files)
        self.notify_tabs()

    def remove_file(self, index):
        if not (0 <= index < len(self.current_files)):
            return
        del self.current_files[index]
        if not self.current_files:
            self.clear_files()
            return
        self.file_path_label.setText(f"Selected: {len(self.current_files)} files")
        self.drop_label.set_files(self.current_files)
        self.notify_tabs()

    def clear_files(self):
        self.current_files = []
        self.file_path_label.setText("No files selected")
        self.drop_label.clear_files()
        self.notify_tabs()

    def browse_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Files (*)")
        if file_paths:
            self.on_files_dropped(file_paths)
            
    def on_tab_changed(self, index):
        preview = getattr(self.tabs.currentWidget(), 'preview_widget', None)
        self.preview_stack.setCurrentWidget(preview or self.file_preview)
        self.notify_tabs()
        
    def notify_tabs(self):
        current_widget = self.tabs.currentWidget()
        if self.preview_stack.currentWidget() is self.file_preview:
            self.file_preview.show_files(self.current_files)
        if hasattr(current_widget, 'on_global_files_changed'):
            current_widget.on_global_files_changed()
            
    def on_export_clicked(self):
        current_widget = self.tabs.currentWidget()
        if hasattr(current_widget, 'export'):
            current_widget.export()

    def set_export_enabled(self, enabled):
        self.export_btn.setEnabled(enabled)

    def set_status(self, message):
        self.global_status_label.setText(message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
