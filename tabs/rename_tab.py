from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QPushButton, QLabel, QHBoxLayout, QFileDialog, QMessageBox, QComboBox
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
        settings_group = QGroupBox("Rename Settings")
        settings_layout = QVBoxLayout()
        
        order_layout = QHBoxLayout()
        order_layout.addWidget(QLabel("Order By:"))
        self.order_combo = QComboBox()
        self.order_combo.addItems(["Name (Alphanumerical)", "Date Created", "Date Modified"])
        order_layout.addWidget(self.order_combo)
        settings_layout.addLayout(order_layout)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        layout.addStretch()

        self.rename_current_files = []

    def on_global_files_changed(self):
        self.rename_current_files = self.main_window.current_files
        self.main_window.set_export_enabled(bool(self.rename_current_files))

    def export(self):
        if not self.rename_current_files:
            return

        override_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()
        order_by = self.order_combo.currentText()

        self.rename_thread = RenameWorkerThread(self.rename_current_files, override_name, start_index, order_by)
        self.rename_thread.finished.connect(self.on_rename_finished)
        self.rename_thread.progress.connect(self.update_rename_status)
        
        self.main_window.set_export_enabled(False)
        self.main_window.set_status("Starting...")
        self.rename_thread.start()

    def update_rename_status(self, message):
        self.main_window.set_status(message)

    def on_rename_finished(self, success, message):
        self.main_window.set_export_enabled(True)
        self.main_window.set_status(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
            self.main_window.clear_files()
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)
