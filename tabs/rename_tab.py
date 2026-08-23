from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QPushButton, QLabel, QHBoxLayout, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt
from components import MultiDragDropLabel
from workers import RenameWorkerThread

class RenameTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Settings Section
        
        layout.addStretch()

        # 3. Action Section
        self.rename_process_btn = QPushButton("Batch Rename Files")
        self.rename_process_btn.setFixedHeight(40)
        self.rename_process_btn.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.rename_process_btn.clicked.connect(self.process_rename_files)
        self.rename_process_btn.setEnabled(False)
        layout.addWidget(self.rename_process_btn)

        self.rename_status_label = QLabel("")
        self.rename_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.rename_status_label)

        self.rename_current_files = []

    def on_global_files_changed(self):
        self.rename_current_files = self.main_window.current_files
        self.rename_process_btn.setEnabled(bool(self.rename_current_files))

    def process_rename_files(self):
        if not self.rename_current_files:
            return

        override_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()

        self.rename_thread = RenameWorkerThread(self.rename_current_files, override_name, start_index)
        self.rename_thread.finished.connect(self.on_rename_finished)
        self.rename_thread.progress.connect(self.update_rename_status)
        
        self.rename_process_btn.setEnabled(False)
        self.rename_status_label.setText("Starting...")
        self.rename_thread.start()

    def update_rename_status(self, message):
        self.rename_status_label.setText(message)

    def on_rename_finished(self, success, message):
        self.rename_process_btn.setEnabled(True)
        self.rename_status_label.setText(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
            self.main_window.clear_files()
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)
