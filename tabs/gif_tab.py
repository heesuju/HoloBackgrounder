from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QPushButton, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QFormLayout, QCheckBox, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt
from components import DragDropLabel
from workers import WorkerThread

class GifTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

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

        default_name = self.main_window.override_name_input.text().strip()
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
