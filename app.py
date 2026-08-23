import sys
import os
import tempfile
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QFileDialog, QSpinBox, QDoubleSpinBox, QMessageBox,
                             QGroupBox, QFormLayout, QCheckBox, QTabWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

import change_bg
import gif_to_mp4
import split_image

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
                if any(file_path.endswith(ext) for ext in self.file_types):
                    event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if any(file_path.lower().endswith(ext) for ext in self.file_types):
                self.fileDropped.emit(file_path)

class WorkerThread(QThread):
    finished = pyqtSignal(bool, str) # Success, Message
    progress = pyqtSignal(str)

    def __init__(self, input_path, output_path, bg_color, threshold, loop_count, replace_bg, pad_frames):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.bg_color = bg_color
        self.threshold = threshold
        self.loop_count = loop_count
        self.replace_bg = replace_bg
        self.pad_frames = pad_frames

    def run(self):
        try:
            self.progress.emit("Processing video...")
            gif_to_mp4.process_video(
                self.input_path, 
                self.output_path, 
                self.loop_count, 
                replace_bg=self.replace_bg,
                bg_color_hex=self.bg_color,
                threshold=self.threshold,
                pad_frames=self.pad_frames
            )
            self.finished.emit(True, f"Successfully saved to {self.output_path}")
        except Exception as e:
            self.finished.emit(False, str(e))

class SplitImageWorkerThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def __init__(self, input_path, output_dir, min_area, min_alpha, override_name, start_index):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.min_area = min_area
        self.min_alpha = min_alpha
        self.override_name = override_name
        self.start_index = start_index

    def run(self):
        try:
            self.progress.emit("Splitting image...")
            saved_files = split_image.split_and_save_shapes(self.input_path, self.output_dir, self.min_area, self.min_alpha, self.override_name, self.start_index)
            self.finished.emit(True, f"Successfully extracted {len(saved_files)} shapes to {self.output_dir}")
        except Exception as e:
            self.finished.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Processor")
        self.setGeometry(100, 100, 550, 500)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Common Output Section
        common_group = QGroupBox("Common Output Settings")
        common_layout = QFormLayout()

        self.override_name_input = QLineEdit("")
        self.override_name_input.setPlaceholderText("Optional: e.g., 'icon' or 'video_name'")
        self.override_name_input.setToolTip("Overrides the base filename for both MP4 saving and Image Splitting.")
        common_layout.addRow("Override Base Name:", self.override_name_input)

        self.start_index_input = QSpinBox()
        self.start_index_input.setRange(0, 100000)
        self.start_index_input.setValue(1)
        self.start_index_input.setToolTip("Starting index for Image Splitting output (e.g. part_1, part_2).")
        common_layout.addRow("Start Index (Splitter):", self.start_index_input)

        common_group.setLayout(common_layout)
        main_layout.addWidget(common_group)
        
        self.init_gif_tab()
        self.init_split_tab()

    def init_gif_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 1. Input File Section
        input_group = QGroupBox("Input GIF/WEBM")
        input_layout = QVBoxLayout()
        
        self.drop_label = DragDropLabel(file_types=['.gif', '.webm'])
        self.drop_label.fileDropped.connect(self.on_file_dropped)
        input_layout.addWidget(self.drop_label)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
        input_layout.addWidget(browse_btn)
        
        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setWordWrap(True)
        input_layout.addWidget(self.file_path_label)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 2. Settings Section
        settings_group = QGroupBox("Settings")
        form_layout = QFormLayout()

        self.replace_bg_check = QCheckBox("Replace Background Color")
        self.replace_bg_check.setChecked(True)
        self.replace_bg_check.toggled.connect(self.toggle_bg_inputs)
        form_layout.addRow(self.replace_bg_check)

        self.color_input = QLineEdit("#ffffff")
        self.color_input.setPlaceholderText("#RRGGBB")
        form_layout.addRow("Background Color (Hex):", self.color_input)

        self.threshold_input = QSpinBox()
        self.threshold_input.setRange(0, 255)
        self.threshold_input.setValue(50)
        self.threshold_input.setToolTip("Tolerance for color matching (0-255)")
        form_layout.addRow("Color Threshold:", self.threshold_input)

        self.loop_input = QDoubleSpinBox()
        self.loop_input.setRange(0.1, 100.0)
        self.loop_input.setValue(1.0)
        self.loop_input.setSingleStep(0.1)
        form_layout.addRow("Loop Count:", self.loop_input)

        self.pad_frames_input = QSpinBox()
        self.pad_frames_input.setRange(0, 100)
        self.pad_frames_input.setValue(0)
        self.pad_frames_input.setToolTip("Add duplicate copies of the last frame to prevent skipping on some hardware.")
        form_layout.addRow("Pad Last Frame (Count):", self.pad_frames_input)

        settings_group.setLayout(form_layout)
        layout.addWidget(settings_group)

        # 3. Action Section
        self.process_btn = QPushButton("Process and Save As MP4")
        self.process_btn.setFixedHeight(40)
        self.process_btn.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.process_btn.clicked.connect(self.process_file)
        self.process_btn.setEnabled(False)
        layout.addWidget(self.process_btn)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.current_file = None
        self.tabs.addTab(tab, "GIF to MP4")

    def init_split_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 1. Input File Section
        input_group = QGroupBox("Input PNG/WEBP Image")
        input_layout = QVBoxLayout()
        
        self.split_drop_label = DragDropLabel(text="Drag and Drop PNG/WEBP file here\nor\nClick 'Browse' to select", file_types=['.png', '.webp'])
        self.split_drop_label.fileDropped.connect(self.on_split_file_dropped)
        input_layout.addWidget(self.split_drop_label)

        btn_layout = QHBoxLayout()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_split_file)
        btn_layout.addWidget(browse_btn)
        
        self.split_clear_btn = QPushButton("Clear")
        self.split_clear_btn.clicked.connect(self.clear_split_file)
        self.split_clear_btn.setEnabled(False)
        btn_layout.addWidget(self.split_clear_btn)
        
        input_layout.addLayout(btn_layout)
        
        self.split_file_path_label = QLabel("No file selected")
        self.split_file_path_label.setWordWrap(True)
        input_layout.addWidget(self.split_file_path_label)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 2. Settings Section
        split_settings_group = QGroupBox("Settings")
        split_form_layout = QFormLayout()

        self.split_min_area_input = QSpinBox()
        self.split_min_area_input.setRange(1, 100000)
        self.split_min_area_input.setValue(50)
        self.split_min_area_input.setToolTip("Minimum area (in pixels) to be considered a shape, used to filter out noise.")
        split_form_layout.addRow("Minimum Area:", self.split_min_area_input)

        self.split_min_alpha_input = QSpinBox()
        self.split_min_alpha_input.setRange(1, 255)
        self.split_min_alpha_input.setValue(10)
        self.split_min_alpha_input.setToolTip("Minimum alpha value (0-255) to be considered opaque.")
        split_form_layout.addRow("Minimum Alpha Threshold:", self.split_min_alpha_input)

        split_settings_group.setLayout(split_form_layout)
        layout.addWidget(split_settings_group)
        
        layout.addStretch()

        # 3. Action Section
        self.split_process_btn = QPushButton("Process and Extract Shapes")
        self.split_process_btn.setFixedHeight(40)
        self.split_process_btn.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.split_process_btn.clicked.connect(self.process_split_file)
        self.split_process_btn.setEnabled(False)
        layout.addWidget(self.split_process_btn)

        self.split_status_label = QLabel("")
        self.split_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.split_status_label)

        self.split_current_file = None
        self.tabs.addTab(tab, "Image Shape Splitter")

    # GIF Tab Methods
    def on_file_dropped(self, file_path):
        self.current_file = file_path
        self.file_path_label.setText(f"Selected: {file_path}")
        self.process_btn.setEnabled(True)
        self.drop_label.setText("File Selected")
        self.drop_label.setStyleSheet("border-color: #55cc55; background-color: #e0ffe0; color: #005500; border-style: solid;")

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "GIF/WEBM Files (*.gif *.webm);;GIF Files (*.gif);;WEBM Files (*.webm)")
        if file_path:
            self.on_file_dropped(file_path)

    def toggle_bg_inputs(self, checked):
        self.color_input.setEnabled(checked)
        self.threshold_input.setEnabled(checked)

    def process_file(self):
        if not self.current_file:
            return

        default_name = self.override_name_input.text().strip()
        if default_name:
            if not default_name.lower().endswith('.mp4'):
                default_name += ".mp4"
        else:
            default_name = ""

        output_path, _ = QFileDialog.getSaveFileName(self, "Save MP4", default_name, "MP4 Files (*.mp4)")
        if not output_path:
            return

        bg_color = self.color_input.text()
        threshold = self.threshold_input.value()
        loop_count = self.loop_input.value()
        pad_frames = self.pad_frames_input.value()
        replace_bg = self.replace_bg_check.isChecked()

        self.thread = WorkerThread(self.current_file, output_path, bg_color, threshold, loop_count, replace_bg, pad_frames)
        self.thread.finished.connect(self.on_finished)
        self.thread.progress.connect(self.update_status)
        
        self.process_btn.setEnabled(False)
        self.drop_label.setEnabled(False)
        self.replace_bg_check.setEnabled(False)
        self.status_label.setText("Starting...")
        self.thread.start()

    def update_status(self, message):
        self.status_label.setText(message)

    def on_finished(self, success, message):
        self.process_btn.setEnabled(True)
        self.drop_label.setEnabled(True)
        self.replace_bg_check.setEnabled(True)
        self.status_label.setText(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)

    # Split Tab Methods
    def on_split_file_dropped(self, file_path):
        self.split_current_file = file_path
        self.split_file_path_label.setText(f"Selected: {file_path}")
        self.split_process_btn.setEnabled(True)
        self.split_clear_btn.setEnabled(True)
        self.split_drop_label.setText("File Selected")
        self.split_drop_label.setStyleSheet("border-color: #55cc55; background-color: #e0ffe0; color: #005500; border-style: solid;")

    def clear_split_file(self):
        self.split_current_file = None
        self.split_file_path_label.setText("No file selected")
        self.split_process_btn.setEnabled(False)
        self.split_clear_btn.setEnabled(False)
        self.split_drop_label.setText("Drag and Drop PNG/WEBP file here\nor\nClick 'Browse' to select")
        self.split_drop_label.setStyleSheet("""
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

    def browse_split_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "Image Files (*.png *.webp);;PNG Files (*.png);;WEBP Files (*.webp)")
        if file_path:
            self.on_split_file_dropped(file_path)

    def process_split_file(self):
        if not self.split_current_file:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        min_area = self.split_min_area_input.value()
        min_alpha = self.split_min_alpha_input.value()
        override_name = self.override_name_input.text()
        start_index = self.start_index_input.value()

        self.split_thread = SplitImageWorkerThread(self.split_current_file, output_dir, min_area, min_alpha, override_name, start_index)
        self.split_thread.finished.connect(self.on_split_finished)
        self.split_thread.progress.connect(self.update_split_status)
        
        self.split_process_btn.setEnabled(False)
        self.split_drop_label.setEnabled(False)
        self.split_status_label.setText("Starting...")
        self.split_thread.start()

    def update_split_status(self, message):
        self.split_status_label.setText(message)

    def on_split_finished(self, success, message):
        self.split_process_btn.setEnabled(True)
        self.split_drop_label.setEnabled(True)
        self.split_status_label.setText(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
