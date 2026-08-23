import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit, QSpinBox, QTabWidget

from tabs.gif_tab import GifTab
from tabs.split_tab import SplitTab
from tabs.rename_tab import RenameTab
from tabs.transparency_tab import TransparencyTab

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
        common_layout.addRow("Start Index (Splitter / Renamer):", self.start_index_input)

        common_group.setLayout(common_layout)
        main_layout.addWidget(common_group)
        
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
