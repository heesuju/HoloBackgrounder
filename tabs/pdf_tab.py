from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt
from workers import PdfWorkerThread

class PdfTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info_label = QLabel("Click Export to combine all selected images into a single PDF.\nThe images will be ordered exactly as they were added in the file list.\nAll images are preserved in their original size and resolution.")
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)
        
        layout.addStretch()

        self.pdf_current_files = []

    def on_global_files_changed(self):
        self.pdf_current_files = self.main_window.current_files
        self.main_window.set_export_enabled(bool(self.pdf_current_files))

    def export(self):
        if not self.pdf_current_files:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if not file_path:
            return

        self.pdf_thread = PdfWorkerThread(self.pdf_current_files, file_path)
        self.pdf_thread.finished.connect(self.on_pdf_finished)
        self.pdf_thread.progress.connect(self.update_pdf_status)
        
        self.main_window.set_export_enabled(False)
        self.main_window.set_status("Starting PDF creation...")
        self.pdf_thread.start()

    def update_pdf_status(self, message):
        self.main_window.set_status(message)

    def on_pdf_finished(self, success, message):
        self.main_window.set_export_enabled(True)
        self.main_window.set_status(message)
        
        if success:
            QMessageBox.information(self, "Success", "Processing complete!\n" + message)
            self.main_window.clear_files()
        else:
            QMessageBox.critical(self, "Error", "An error occurred:\n" + message)
