from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QPushButton, QLabel, QSpinBox, QHBoxLayout, QFormLayout, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt
from components import DragDropLabel
from workers import SplitImageWorkerThread

class SplitTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

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
        override_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()

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
