import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QGroupBox, 
                             QFormLayout, QLineEdit, QSpinBox, QTabWidget, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog)
from PyQt6.QtCore import pyqtSignal

from components import MultiDragDropLabel
from tabs.gif_tab import GifTab
from tabs.split_tab import SplitTab
from tabs.rename_tab import RenameTab
from tabs.transparency_tab import TransparencyTab

class MainWindow(QMainWindow):
    # Custom signal if we need it, though direct method calling is also fine
    # We will just call a method on the active tab, or all tabs.
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Processor")
        self.setGeometry(100, 100, 600, 700)
        
        self.current_files = []

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 1. Global Input Section
        input_group = QGroupBox("Global Input Files (Drag & Drop)")
        input_layout = QVBoxLayout()
        
        self.drop_label = MultiDragDropLabel(text="Drag and Drop multiple files here\nor\nClick 'Browse' to select")
        self.drop_label.filesDropped.connect(self.on_files_dropped)
        input_layout.addWidget(self.drop_label)

        btn_layout = QHBoxLayout()
        browse_btn = QPushButton("Browse Files")
        browse_btn.clicked.connect(self.browse_files)
        btn_layout.addWidget(browse_btn)
        
        self.clear_btn = QPushButton("Clear Files")
        self.clear_btn.clicked.connect(self.clear_files)
        self.clear_btn.setEnabled(False)
        btn_layout.addWidget(self.clear_btn)
        
        input_layout.addLayout(btn_layout)
        
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
        
        self.init_tabs()

    def init_tabs(self):
        self.gif_tab = GifTab(self)
        self.split_tab = SplitTab(self)
        self.rename_tab = RenameTab(self)
        self.transparency_tab = TransparencyTab(self)

        self.tabs.addTab(self.gif_tab, "GIF to MP4")
        self.tabs.addTab(self.split_tab, "Image Shape Splitter")
        self.tabs.addTab(self.rename_tab, "Batch Renamer")
        self.tabs.addTab(self.transparency_tab, "Color to Transparency")
        
    def on_files_dropped(self, file_paths):
        self.current_files = file_paths
        self.file_path_label.setText(f"Selected: {len(file_paths)} files")
        self.clear_btn.setEnabled(True)
        self.drop_label.setText(f"{len(file_paths)} Files Selected")
        self.drop_label.setStyleSheet("border-color: #55cc55; background-color: #e0ffe0; color: #005500; border-style: solid;")
        self.notify_tabs()

    def clear_files(self):
        self.current_files = []
        self.file_path_label.setText("No files selected")
        self.clear_btn.setEnabled(False)
        self.drop_label.setText("Drag and Drop multiple files here\nor\nClick 'Browse' to select")
        self.drop_label.setStyleSheet("""
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
        self.notify_tabs()

    def browse_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Files (*)")
        if file_paths:
            self.on_files_dropped(file_paths)
            
    def on_tab_changed(self, index):
        self.notify_tabs()
        
    def notify_tabs(self):
        current_widget = self.tabs.currentWidget()
        if hasattr(current_widget, 'on_global_files_changed'):
            current_widget.on_global_files_changed()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
