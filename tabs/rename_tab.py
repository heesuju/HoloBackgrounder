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

        # 1. Input File Section
        input_group = QGroupBox("Input Files (Any format)")
        input_layout = QVBoxLayout()
        
        self.rename_drop_label = MultiDragDropLabel(text="Drag and Drop multiple files here\nor\nClick 'Browse' to select")
        self.rename_drop_label.filesDropped.connect(self.on_rename_files_dropped)
        input_layout.addWidget(self.rename_drop_label)

        btn_layout = QHBoxLayout()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_rename_files)
        btn_layout.addWidget(browse_btn)
        
        self.rename_clear_btn = QPushButton("Clear")
        self.rename_clear_btn.clicked.connect(self.clear_rename_files)
        self.rename_clear_btn.setEnabled(False)
        btn_layout.addWidget(self.rename_clear_btn)
        
        input_layout.addLayout(btn_layout)
        
        self.rename_file_path_label = QLabel("No files selected")
        self.rename_file_path_label.setWordWrap(True)
        input_layout.addWidget(self.rename_file_path_label)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
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

    def on_rename_files_dropped(self, file_paths):
        self.rename_current_files = file_paths
        self.rename_file_path_label.setText(f"Selected: {len(file_paths)} files")
        self.rename_process_btn.setEnabled(True)
        self.rename_clear_btn.setEnabled(True)
        self.rename_drop_label.setText(f"{len(file_paths)} Files Selected")
        self.rename_drop_label.setStyleSheet("border-color: #55cc55; background-color: #e0ffe0; color: #005500; border-style: solid;")

    def clear_rename_files(self):
        self.rename_current_files = []
        self.rename_file_path_label.setText("No files selected")
        self.rename_process_btn.setEnabled(False)
        self.rename_clear_btn.setEnabled(False)
        self.rename_drop_label.setText("Drag and Drop multiple files here\nor\nClick 'Browse' to select")
        self.rename_drop_label.setStyleSheet("""
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

    def browse_rename_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Files (*)")
        if file_paths:
            self.on_rename_files_dropped(file_paths)

    def process_rename_files(self):
        if not self.rename_current_files:
            return

        override_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()

        self.rename_thread = RenameWorkerThread(self.rename_current_files, override_name, start_index)
        self.rename_thread.finished.connect(self.on_rename_finished)
        self.rename_thread.progress.connect(self.update_rename_status)
        
        self.rename_process_btn.setEnabled(False)
        self.rename_drop_label.setEnabled(False)
        self.rename_status_label.setText("Starting...")
        self.rename_thread.start()

    def update_rename_status(self, message):
        self.rename_status_label.setText(message)

    def on_rename_finished(self, success, message):
        self.rename_process_btn.setEnabled(True)
        self.rename_drop_label.setEnabled(True)
        self.rename_status_label.setText(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
            self.clear_rename_files()
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)
