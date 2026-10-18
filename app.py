import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QGroupBox,
                             QFormLayout, QLineEdit, QSpinBox, QPushButton, QLabel, QFileDialog,
                             QSplitter, QStackedWidget, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from components import MultiDragDropLabel, FilePreview
from tabs.gif_tab import GifTab
from tabs.split_tab import SplitTab
from tabs.rename_tab import RenameTab
from tabs.transparency_tab import TransparencyTab
from tabs.outline_tab import OutlineTab
from tabs.crop_tab import CropTab
from tabs.pdf_tab import PdfTab
from tabs.pixel_tab import PixelTab
from tabs.icon_tab import IconTab
from tabs.resize_tab import ResizeTab
from tabs.region_tab import RegionTab

IMAGES = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
IMAGES_TIFF = IMAGES + ('.tif', '.tiff')

# Sidebar layout: (group, [(label, tab class, accepted extensions or None for any file)])
# Extensions mirror what each tab picks out of the global file list; tools that can't
# use any of the selected files are greyed out.
TOOL_GROUPS = [
    ("Convert", [
        ("GIF to MP4", GifTab, ('.gif', '.webm')),
        ("Images to PDF", PdfTab, IMAGES_TIFF + ('.gif',)),
    ]),
    ("Resize & Crop", [
        ("Batch Crop", CropTab, IMAGES),
        ("Lossless Resize", ResizeTab, IMAGES_TIFF),
        ("Region Swap", RegionTab, IMAGES_TIFF),
        ("Image Shape Splitter", SplitTab, ('.png', '.webp')),
    ]),
    ("Transparency", [
        ("Color to Transparency", TransparencyTab, IMAGES),
        ("Outline Generator", OutlineTab, ('.png', '.webp')),
    ]),
    ("Stylize", [
        ("픽셀화", PixelTab, IMAGES),
        ("Icon Generator", IconTab, IMAGES),
    ]),
    ("Files", [
        ("Batch Renamer", RenameTab, None),
    ]),
]

TOOL_ROLE = Qt.ItemDataRole.UserRole

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Processor")
        self.setGeometry(100, 100, 1400, 850)
        
        self.current_files = []

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # 0. Tool sidebar (grouped)
        self.tool_list = QListWidget()
        self.tool_list.setFixedWidth(190)
        self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tool_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tool_list.setStyleSheet("""
            QListWidget { border: none; background: #f4f4f4; outline: 0; padding-top: 6px; }
            QListWidget::item { padding: 5px 8px; }
            QListWidget::item:selected { background: #d6e8ff; color: #000; border-radius: 4px; }
        """)
        self.tool_list.currentItemChanged.connect(self.on_tool_changed)

        left_widget = QWidget()
        main_layout = QVBoxLayout(left_widget)
        
        # 1. Global Input Section
        input_group = QGroupBox("Global Input Files (Drag & Drop)")
        input_layout = QVBoxLayout()
        
        self.drop_label = MultiDragDropLabel(text="Drag and Drop multiple files here\nor\nClick to browse")
        self.drop_label.filesDropped.connect(self.on_files_dropped)
        self.drop_label.clicked.connect(self.browse_files)
        self.drop_label.removeRequested.connect(self.remove_file)
        input_layout.addWidget(self.drop_label)

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
        
        # 3. Current tool's settings
        self.tool_stack = QStackedWidget()
        main_layout.addWidget(self.tool_stack, 1)

        # 4. Global Export Section
        self.export_btn = QPushButton("Export")
        self.export_btn.setFixedHeight(45)
        self.export_btn.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.export_btn.clicked.connect(self.on_export_clicked)
        self.export_btn.setEnabled(False)
        main_layout.addWidget(self.export_btn)

        self.global_status_label = QLabel("")
        self.global_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.global_status_label)

        # 5. Preview (right side) - shows the current tab's preview widget
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        self.preview_stack = QStackedWidget()
        self.file_preview = FilePreview()
        self.preview_stack.addWidget(self.file_preview)
        preview_layout.addWidget(self.preview_stack)
        hint = QLabel("Scroll: zoom  ·  Middle-drag: pan  ·  Middle double-click: fit")
        hint.setStyleSheet("color: #777;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(hint)
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)

        splitter.addWidget(self.tool_list)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setCollapsible(0, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([190, 540, 820])

        self.init_tools()

    def init_tools(self):
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(max(1, header_font.pointSize() - 1))

        self.tool_items = []
        for group, tools in TOOL_GROUPS:
            header = QListWidgetItem(group.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setFont(header_font)
            header.setForeground(QColor(120, 120, 120))
            self.tool_list.addItem(header)

            for label, tab_cls, accepts in tools:
                tab = tab_cls(self)
                self.tool_stack.addWidget(tab)
                preview = getattr(tab, 'preview_widget', None)
                if preview is not None:
                    self.preview_stack.addWidget(preview)

                item = QListWidgetItem("    " + label)
                item.setData(TOOL_ROLE, (tab, accepts))
                self.tool_list.addItem(item)
                self.tool_items.append(item)

        self.tool_list.setCurrentItem(self.tool_items[0])

    def current_tool(self):
        return self.tool_stack.currentWidget()

    def tool_accepts_files(self, accepts):
        if not self.current_files or accepts is None:
            return True
        return any(f.lower().endswith(accepts) for f in self.current_files)

    def update_tool_availability(self):
        """Grey out tools that can't use any selected file. If the current tool got
        greyed out, switch to the first usable one; returns True when it switched."""
        for item in self.tool_items:
            _, accepts = item.data(TOOL_ROLE)
            flags = Qt.ItemFlag.ItemIsSelectable
            if self.tool_accepts_files(accepts):
                flags |= Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)

        current = self.tool_list.currentItem()
        if current is None or not current.flags() & Qt.ItemFlag.ItemIsEnabled:
            enabled = [i for i in self.tool_items if i.flags() & Qt.ItemFlag.ItemIsEnabled]
            if enabled:
                self.tool_list.setCurrentItem(enabled[0])
                return True
        return False

    def on_files_dropped(self, file_paths):
        import re, os
        def natural_keys(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
        
        self.current_files = sorted(file_paths, key=lambda x: natural_keys(os.path.basename(x)))
        self.file_path_label.setText(f"Selected: {len(self.current_files)} files")
        self.drop_label.set_files(self.current_files)
        self.on_files_changed()

    def remove_file(self, index):
        if not (0 <= index < len(self.current_files)):
            return
        del self.current_files[index]
        if not self.current_files:
            self.clear_files()
            return
        self.file_path_label.setText(f"Selected: {len(self.current_files)} files")
        self.drop_label.set_files(self.current_files)
        self.on_files_changed()

    def clear_files(self):
        self.current_files = []
        self.file_path_label.setText("No files selected")
        self.drop_label.clear_files()
        self.on_files_changed()

    def on_files_changed(self):
        # Switching tools already notifies the newly selected tool
        if not self.update_tool_availability():
            self.notify_tabs()

    def browse_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Files (*)")
        if file_paths:
            self.on_files_dropped(file_paths)
            
    def on_tool_changed(self, item, _previous):
        if item is None or item.data(TOOL_ROLE) is None:
            return
        tab, _ = item.data(TOOL_ROLE)
        self.tool_stack.setCurrentWidget(tab)
        preview = getattr(tab, 'preview_widget', None)
        self.preview_stack.setCurrentWidget(preview or self.file_preview)
        self.notify_tabs()
        
    def notify_tabs(self):
        current_widget = self.current_tool()
        if self.preview_stack.currentWidget() is self.file_preview:
            # Preview the first file this tool would actually use
            _, accepts = self.tool_list.currentItem().data(TOOL_ROLE)
            usable = [f for f in self.current_files if accepts is None or f.lower().endswith(accepts)]
            self.file_preview.show_files(usable)
        if hasattr(current_widget, 'on_global_files_changed'):
            current_widget.on_global_files_changed()
            
    def on_export_clicked(self):
        current_widget = self.current_tool()
        if hasattr(current_widget, 'export'):
            current_widget.export()

    def set_export_enabled(self, enabled):
        self.export_btn.setEnabled(enabled)

    def set_status(self, message):
        self.global_status_label.setText(message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
