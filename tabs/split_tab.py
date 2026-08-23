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

        # Settings Section
        
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

        self.split_current_file = None

    def on_global_files_changed(self):
        valid_file = self.get_valid_file()
        self.main_window.set_export_enabled(bool(valid_file))

    def get_valid_file(self):
        for f in self.main_window.current_files:
            if f.lower().endswith(('.png', '.webp')):
                return f
        return None

    def export(self):
        current_file = self.get_valid_file()
        if not current_file:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        min_area = self.split_min_area_input.value()
        min_alpha = self.split_min_alpha_input.value()
        override_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()

        self.split_thread = SplitImageWorkerThread(current_file, output_dir, min_area, min_alpha, override_name, start_index)
        self.split_thread.finished.connect(self.on_split_finished)
        self.split_thread.progress.connect(self.update_split_status)
        
        self.main_window.set_export_enabled(False)
        self.main_window.set_status("Starting...")
        self.split_thread.start()

    def update_split_status(self, message):
        self.main_window.set_status(message)

    def on_split_finished(self, success, message):
        self.main_window.set_export_enabled(True)
        self.main_window.set_status(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)
