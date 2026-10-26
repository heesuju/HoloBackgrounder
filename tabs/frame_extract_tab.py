import os
from PIL import Image
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QGroupBox,
    QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QCheckBox,
    QPushButton, QMessageBox, QProgressBar, QScrollArea, QFrame, QSizePolicy,
    QGraphicsScene, QGraphicsPixmapItem, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QBrush, QColor, QFont, QIcon

import frame_extractor
from workers import FrameExtractWorkerThread, FrameScanWorkerThread
from components import ZoomableGraphicsView, checkerboard_pixmap

SUPPORTED_EXTS = ('.mp4', '.gif', '.webm', '.avi', '.mov', '.mkv', '.m4v', '.wmv')


def pil_to_qimage(pil_img):
    """Converts a PIL Image to a QImage."""
    if pil_img is None:
        return QImage()
    rgba_img = pil_img.convert("RGBA")
    data = rgba_img.tobytes("raw", "RGBA")
    return QImage(data, rgba_img.width, rgba_img.height, QImage.Format.Format_RGBA8888).copy()


class FrameExtractTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.valid_files = []
        self.current_file = None
        self.current_media_info = None

        self.current_frame_index = 0
        self.current_pil_img = None
        self.current_qimage = None

        # Scanned unique frames list of dicts: [{'index': ..., 'timestamp': ..., 'diff_pct': ..., 'thumbnail': ...}]
        self.unique_frames = []
        self.unique_indices = []

        # Worker threads
        self.scan_worker = None
        self.extract_worker = None

        # Playback timer
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self.advance_playback_frame)
        self.is_playing = False

        self._updating_controls = False

        self.init_ui()
        self.init_preview_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Info / Header Section
        info_group = QGroupBox("Extract Different Frames")
        info_layout = QVBoxLayout()
        desc = QLabel(
            "Extracts distinct/unique frames from videos or animated GIFs into separate image files.\n"
            "Automatically filters out identical hold frames and repeated animations using difference detection."
        )
        desc.setWordWrap(True)
        info_layout.addWidget(desc)

        self.file_combo = QComboBox()
        self.file_combo.setToolTip("Select which video/GIF to preview and configure")
        self.file_combo.currentIndexChanged.connect(self.on_file_selection_changed)
        info_layout.addWidget(self.file_combo)

        self.media_info_label = QLabel("No video or GIF selected")
        self.media_info_label.setStyleSheet("color: #444; font-weight: bold;")
        info_layout.addWidget(self.media_info_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 2. Difference Detection Settings
        diff_group = QGroupBox("Difference & Deduplication Settings")
        diff_form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Skip Consecutive Duplicates (Animation/Video)", "consecutive")
        self.mode_combo.addItem("Skip All Duplicates (Global Unique Frames)", "global")
        self.mode_combo.addItem("All Frames (No Deduplication)", "all")
        self.mode_combo.setToolTip(
            "Consecutive: Drops static hold frames where nothing moved.\n"
            "Global Unique: Drops any frame identical to an earlier frame (great for loops/walk cycles).\n"
            "All Frames: Extracts every sampled frame."
        )
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        diff_form.addRow("Extraction Mode:", self.mode_combo)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Low Video Noise (1.0% - MP4 / WebM)", 1.0)
        self.preset_combo.addItem("Exact Match (0.0% - Lossless / GIF)", 0.0)
        self.preset_combo.addItem("Medium Tolerance (3.0%)", 3.0)
        self.preset_combo.addItem("High Tolerance (5.0%)", 5.0)
        self.preset_combo.addItem("Custom...", -1)
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        diff_form.addRow("Preset:", self.preset_combo)

        thresh_layout = QHBoxLayout()
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 200) # 0.0% to 20.0%
        self.threshold_slider.setValue(10)     # 1.0%
        self.threshold_slider.valueChanged.connect(self.on_slider_changed)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 20.0)
        self.threshold_spin.setSingleStep(0.1)
        self.threshold_spin.setValue(1.0)
        self.threshold_spin.setSuffix(" %")
        self.threshold_spin.setToolTip("Frame difference threshold. 0% is exact match. 1-2% handles video compression noise.")
        self.threshold_spin.valueChanged.connect(self.on_spin_changed)

        thresh_layout.addWidget(self.threshold_slider, 2)
        thresh_layout.addWidget(self.threshold_spin, 1)
        diff_form.addRow("Diff Threshold:", thresh_layout)

        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 100)
        self.step_spin.setValue(1)
        self.step_spin.setToolTip("Check every Nth frame (1 = check every frame, 2 = every 2nd frame)")
        diff_form.addRow("Frame Step:", self.step_spin)

        # Scan button & progress
        scan_layout = QHBoxLayout()
        self.scan_btn = QPushButton("🔍 Scan Unique Frames")
        self.scan_btn.setToolTip("Analyze video frames with current threshold to preview all different frames")
        self.scan_btn.clicked.connect(self.start_scan)
        scan_layout.addWidget(self.scan_btn)

        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setVisible(False)
        self.scan_progress_bar.setRange(0, 100)
        scan_layout.addWidget(self.scan_progress_bar)

        diff_form.addRow("", scan_layout)

        self.scan_status_label = QLabel("Click 'Scan Unique Frames' or scrub preview.")
        self.scan_status_label.setStyleSheet("color: #666; font-size: 11px;")
        diff_form.addRow("", self.scan_status_label)

        diff_group.setLayout(diff_form)
        layout.addWidget(diff_group)

        # 3. Output Format Settings
        out_group = QGroupBox("Output Settings")
        out_form = QFormLayout()

        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG (.png) - Lossless with Transparency", "png")
        self.format_combo.addItem("WebP (.webp) - High Compression", "webp")
        self.format_combo.addItem("JPEG (.jpg) - Standard Photo", "jpg")
        self.format_combo.addItem("BMP (.bmp) - Uncompressed", "bmp")
        self.format_combo.currentIndexChanged.connect(self.on_format_changed)
        out_form.addRow("Image Format:", self.format_combo)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(95)
        self.quality_spin.setSuffix(" %")
        self.quality_spin.setToolTip("Image compression quality (1-100)")
        self.quality_spin.setEnabled(False) # Enabled for jpg/webp
        out_form.addRow("Quality:", self.quality_spin)

        self.padding_combo = QComboBox()
        self.padding_combo.addItem("Auto (Based on frame count)", -1)
        self.padding_combo.addItem("4 digits (0001, 0002)", 4)
        self.padding_combo.addItem("5 digits (00001, 00002)", 5)
        self.padding_combo.addItem("3 digits (001, 002)", 3)
        self.padding_combo.addItem("No padding (1, 2)", 0)
        out_form.addRow("Index Padding:", self.padding_combo)

        self.subfolder_check = QCheckBox("Create dedicated folder for each video")
        self.subfolder_check.setChecked(True)
        self.subfolder_check.setToolTip("Saves images into [video_name]_frames/ subfolder inside output directory")
        out_form.addRow("", self.subfolder_check)

        self.batch_check = QCheckBox("Batch extract all loaded videos")
        self.batch_check.setChecked(True)
        self.batch_check.setToolTip("When exporting, process all videos currently loaded in Global Input")
        out_form.addRow("", self.batch_check)

        out_group.setLayout(out_form)
        layout.addWidget(out_group)

        layout.addStretch()

    def init_preview_ui(self):
        """Creates the right-side preview widget with video scrubbing and filmstrip."""
        self.preview_widget = QWidget()
        preview_layout = QVBoxLayout(self.preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Preview Info Bar
        info_bar = QHBoxLayout()
        self.preview_title_label = QLabel("No Video Loaded")
        self.preview_title_label.setStyleSheet("font-weight: bold; color: #222; font-size: 13px;")
        info_bar.addWidget(self.preview_title_label, 1)

        self.unique_badge = QLabel("")
        self.unique_badge.setStyleSheet(
            "background-color: #2e7d32; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold;"
        )
        self.unique_badge.setVisible(False)
        info_bar.addWidget(self.unique_badge)

        preview_layout.addLayout(info_bar)

        # 2. Main Display Area with Checkerboard for Transparency
        self.view = ZoomableGraphicsView(pan_with_left=True)
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.view.setBackgroundBrush(QBrush(checkerboard_pixmap(16, QColor(230, 230, 230), QColor(200, 200, 200))))
        preview_layout.addWidget(self.view, 1)

        # 3. Playback and Scrubber Controls
        controls_group = QGroupBox("Timeline & Navigation")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(8, 6, 8, 6)

        # Scrubber row
        slider_row = QHBoxLayout()
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        slider_row.addWidget(self.frame_slider, 1)

        self.time_label = QLabel("0 / 0 (00:00.00)")
        self.time_label.setFixedWidth(140)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.time_label.setStyleSheet("font-family: monospace; font-size: 12px; font-weight: bold;")
        slider_row.addWidget(self.time_label)

        controls_layout.addLayout(slider_row)

        # Navigation buttons row
        btn_row = QHBoxLayout()

        self.first_btn = QPushButton("⏮ First")
        self.first_btn.setFixedWidth(65)
        self.first_btn.clicked.connect(self.go_first_frame)
        btn_row.addWidget(self.first_btn)

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setFixedWidth(65)
        self.prev_btn.clicked.connect(self.go_prev_frame)
        btn_row.addWidget(self.prev_btn)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setFixedWidth(80)
        self.play_btn.setStyleSheet("font-weight: bold;")
        self.play_btn.clicked.connect(self.toggle_play)
        btn_row.addWidget(self.play_btn)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setFixedWidth(65)
        self.next_btn.clicked.connect(self.go_next_frame)
        btn_row.addWidget(self.next_btn)

        self.last_btn = QPushButton("Last ⏭")
        self.last_btn.setFixedWidth(65)
        self.last_btn.clicked.connect(self.go_last_frame)
        btn_row.addWidget(self.last_btn)

        btn_row.addSpacing(15)

        self.prev_diff_btn = QPushButton("⚡ Prev Unique")
        self.prev_diff_btn.setToolTip("Jump to previous different/unique frame")
        self.prev_diff_btn.clicked.connect(self.go_prev_unique)
        btn_row.addWidget(self.prev_diff_btn)

        self.next_diff_btn = QPushButton("Next Unique ⚡")
        self.next_diff_btn.setToolTip("Jump to next different/unique frame")
        self.next_diff_btn.clicked.connect(self.go_next_unique)
        btn_row.addWidget(self.next_diff_btn)

        self.snap_unique_check = QCheckBox("Snap Slider to Unique Frames Only")
        self.snap_unique_check.setToolTip("When checked, slider steps directly between detected unique frames")
        btn_row.addWidget(self.snap_unique_check)

        controls_layout.addLayout(btn_row)
        preview_layout.addWidget(controls_group)

        # 4. Unique Frames Filmstrip Area
        self.filmstrip_group = QGroupBox("Detected Unique Frames (Click to View)")
        filmstrip_layout = QVBoxLayout(self.filmstrip_group)
        filmstrip_layout.setContentsMargins(6, 4, 6, 4)

        self.filmstrip_scroll = QScrollArea()
        self.filmstrip_scroll.setFixedHeight(115)
        self.filmstrip_scroll.setWidgetResizable(True)
        self.filmstrip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.filmstrip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.filmstrip_container = QWidget()
        self.filmstrip_row = QHBoxLayout(self.filmstrip_container)
        self.filmstrip_row.setContentsMargins(4, 4, 4, 4)
        self.filmstrip_row.setSpacing(6)
        self.filmstrip_row.addStretch()

        self.filmstrip_scroll.setWidget(self.filmstrip_container)
        filmstrip_layout.addWidget(self.filmstrip_scroll)

        preview_layout.addWidget(self.filmstrip_group)

        self.update_playback_buttons()

    # --- File Management ---

    def on_global_files_changed(self):
        """Called by MainWindow when files are dropped or cleared."""
        valid = [f for f in self.main_window.current_files if f.lower().endswith(SUPPORTED_EXTS)]
        self.valid_files = valid

        self._updating_controls = True
        self.file_combo.clear()
        for f in valid:
            self.file_combo.addItem(os.path.basename(f), f)
        self._updating_controls = False

        if valid:
            self.set_current_file(valid[0])
            self.main_window.set_export_enabled(True)
        else:
            self.set_current_file(None)
            self.main_window.set_export_enabled(False)

        self.batch_check.setVisible(len(valid) > 1)
        self.batch_check.setText(f"Batch extract all {len(valid)} loaded videos")

    def on_file_selection_changed(self, idx):
        if self._updating_controls:
            return
        file_path = self.file_combo.currentData()
        self.set_current_file(file_path)

    def set_current_file(self, file_path):
        if self.is_playing:
            self.toggle_play()

        self.current_file = file_path
        self.unique_frames = []
        self.unique_indices = []
        self.clear_filmstrip()

        if not file_path or not os.path.exists(file_path):
            self.current_media_info = None
            self.media_info_label.setText("No video or GIF selected")
            self.preview_title_label.setText("No Video Loaded")
            self.time_label.setText("0 / 0 (00:00.00)")
            self.frame_slider.setRange(0, 0)
            self.pixmap_item.setPixmap(QPixmap())
            self.scene.setSceneRect(0, 0, 0, 0)
            self.unique_badge.setVisible(False)
            self.scan_status_label.setText("No video or GIF selected.")
            self.update_playback_buttons()
            return

        try:
            info = frame_extractor.get_media_info(file_path)
            self.current_media_info = info

            # Update labels
            type_str = "GIF Animation" if info['is_gif'] else "Video"
            self.media_info_label.setText(
                f"{info['filename']}\n"
                f"Type: {type_str} | Res: {info['width']}x{info['height']} | "
                f"FPS: {info['fps']} | Total Frames: {info['total_frames']} ({info['duration']}s)"
            )

            # Auto preset selection: GIF -> Exact Match, Video -> Low Video Noise
            if info['is_gif'] and self.preset_combo.currentIndex() != 1:
                self.preset_combo.setCurrentIndex(1) # Exact Match
            elif not info['is_gif'] and self.preset_combo.currentIndex() != 0:
                self.preset_combo.setCurrentIndex(0) # Low Video Noise

            self.frame_slider.blockSignals(True)
            self.frame_slider.setRange(0, max(0, info['total_frames'] - 1))
            self.frame_slider.setValue(0)
            self.frame_slider.blockSignals(False)

            self.load_frame(0)
            self.update_playback_buttons()

            # Automatically trigger background scan for unique frames
            self.start_scan()

        except Exception as e:
            self.media_info_label.setText(f"Error loading file: {e}")
            self.preview_title_label.setText("Error Loading Media")

    # --- Frame Display & Navigation ---

    def load_frame(self, index):
        if not self.current_file:
            return

        total = self.current_media_info['total_frames'] if self.current_media_info else 1
        index = max(0, min(index, total - 1))
        self.current_frame_index = index

        pil_img, timestamp = frame_extractor.get_frame_at_index(self.current_file, index)
        if pil_img is None:
            return

        self.current_pil_img = pil_img
        self.current_qimage = pil_to_qimage(pil_img)

        # Update scene
        self.scene.setSceneRect(0, 0, self.current_qimage.width(), self.current_qimage.height())
        self.pixmap_item.setPixmap(QPixmap.fromImage(self.current_qimage))
        if self.view._fit:
            self.view.fit_view()

        # Update labels & slider
        fps = self.current_media_info['fps'] if self.current_media_info else 24.0
        minutes = int(timestamp // 60)
        seconds = timestamp % 60
        time_str = f"{minutes:02d}:{seconds:05.2f}"
        self.time_label.setText(f"{index + 1} / {total} ({time_str})")

        fname = self.current_media_info['filename'] if self.current_media_info else ""
        res_str = f"{self.current_qimage.width()}x{self.current_qimage.height()}"
        self.preview_title_label.setText(f"{fname}  ·  Frame {index + 1}/{total}  ·  {res_str}")

        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(index)
        self.frame_slider.blockSignals(False)

        # Highlight in badge if current frame is one of the detected unique frames
        if index in self.unique_indices:
            u_rank = self.unique_indices.index(index) + 1
            self.unique_badge.setText(f"⚡ Unique Frame #{u_rank}")
            self.unique_badge.setVisible(True)
        else:
            self.unique_badge.setVisible(False)

        self.highlight_filmstrip_thumbnail(index)

    def on_frame_slider_changed(self, value):
        if self.snap_unique_check.isChecked() and self.unique_indices:
            # Snap to closest unique index
            closest = min(self.unique_indices, key=lambda x: abs(x - value))
            self.load_frame(closest)
        else:
            self.load_frame(value)

    def go_first_frame(self):
        self.load_frame(0)

    def go_prev_frame(self):
        self.load_frame(self.current_frame_index - 1)

    def go_next_frame(self):
        self.load_frame(self.current_frame_index + 1)

    def go_last_frame(self):
        if self.current_media_info:
            self.load_frame(self.current_media_info['total_frames'] - 1)

    def go_prev_unique(self):
        if not self.unique_indices:
            self.go_prev_frame()
            return
        prev_candidates = [idx for idx in self.unique_indices if idx < self.current_frame_index]
        if prev_candidates:
            self.load_frame(prev_candidates[-1])
        else:
            self.load_frame(self.unique_indices[0])

    def go_next_unique(self):
        if not self.unique_indices:
            self.go_next_frame()
            return
        next_candidates = [idx for idx in self.unique_indices if idx > self.current_frame_index]
        if next_candidates:
            self.load_frame(next_candidates[0])
        else:
            self.load_frame(self.unique_indices[-1])

    def toggle_play(self):
        if not self.current_file or not self.current_media_info:
            return

        if self.is_playing:
            self.play_timer.stop()
            self.is_playing = False
            self.play_btn.setText("▶ Play")
        else:
            fps = self.current_media_info['fps']
            interval = int(1000.0 / fps) if fps > 0 else 40
            self.play_timer.setInterval(max(15, interval))
            self.play_timer.start()
            self.is_playing = True
            self.play_btn.setText("⏸ Pause")

    def advance_playback_frame(self):
        if not self.current_media_info:
            self.toggle_play()
            return

        total = self.current_media_info['total_frames']
        next_idx = self.current_frame_index + 1
        if next_idx >= total:
            next_idx = 0 # loop
        self.load_frame(next_idx)

    def update_playback_buttons(self):
        enabled = bool(self.current_file and self.current_media_info)
        self.first_btn.setEnabled(enabled)
        self.prev_btn.setEnabled(enabled)
        self.play_btn.setEnabled(enabled)
        self.next_btn.setEnabled(enabled)
        self.last_btn.setEnabled(enabled)
        self.prev_diff_btn.setEnabled(enabled and bool(self.unique_indices))
        self.next_diff_btn.setEnabled(enabled and bool(self.unique_indices))
        self.frame_slider.setEnabled(enabled)
        self.scan_btn.setEnabled(enabled)

    # --- Difference Settings Events ---

    def on_mode_changed(self, _idx):
        self.start_scan()

    def on_preset_changed(self, idx):
        val = self.preset_combo.currentData()
        if val is not None and val >= 0:
            self._updating_controls = True
            self.threshold_spin.setValue(val)
            self.threshold_slider.setValue(int(val * 10))
            self._updating_controls = False
            self.start_scan()

    def on_slider_changed(self, value):
        if self._updating_controls:
            return
        self._updating_controls = True
        val = value / 10.0
        self.threshold_spin.setValue(val)
        self.sync_preset_to_custom()
        self._updating_controls = False

    def on_spin_changed(self, value):
        if self._updating_controls:
            return
        self._updating_controls = True
        self.threshold_slider.setValue(int(value * 10))
        self.sync_preset_to_custom()
        self._updating_controls = False

    def sync_preset_to_custom(self):
        val = self.threshold_spin.value()
        for i in range(self.preset_combo.count() - 1):
            if abs(self.preset_combo.itemData(i) - val) < 0.05:
                self.preset_combo.setCurrentIndex(i)
                return
        self.preset_combo.setCurrentIndex(self.preset_combo.count() - 1) # Custom

    def on_format_changed(self, _idx):
        fmt = self.format_combo.currentData()
        self.quality_spin.setEnabled(fmt in ('jpg', 'webp'))

    # --- Scanning for Unique Frames ---

    def start_scan(self):
        if not self.current_file:
            return

        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_worker.wait()

        mode = self.mode_combo.currentData()
        threshold = self.threshold_spin.value()
        step = self.step_spin.value()

        self.scan_progress_bar.setVisible(True)
        self.scan_progress_bar.setValue(0)
        self.scan_btn.setEnabled(False)
        self.scan_status_label.setText("Analyzing different frames...")

        self.scan_worker = FrameScanWorkerThread(self.current_file, mode, threshold, step)
        self.scan_worker.scan_progress.connect(self.on_scan_progress)
        self.scan_worker.scan_finished.connect(self.on_scan_finished)
        self.scan_worker.start()

    def on_scan_progress(self, current, total):
        if total > 0:
            pct = int((current / total) * 100)
            self.scan_progress_bar.setValue(pct)

    def on_scan_finished(self, items, file_path):
        self.scan_progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)

        if file_path != self.current_file:
            return

        self.unique_frames = items
        self.unique_indices = [x['index'] for x in items]

        total = self.current_media_info['total_frames'] if self.current_media_info else len(items)
        unique_cnt = len(items)
        saved_pct = ((total - unique_cnt) / total * 100) if total > 0 else 0.0

        self.scan_status_label.setText(
            f"Found {unique_cnt} unique frames out of {total} ({saved_pct:.1f}% duplicate reduction)."
        )

        self.update_playback_buttons()
        self.populate_filmstrip()
        self.load_frame(self.current_frame_index)

    # --- Filmstrip Display ---

    def clear_filmstrip(self):
        while self.filmstrip_row.count() > 1:
            item = self.filmstrip_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def populate_filmstrip(self):
        self.clear_filmstrip()
        self.thumb_widgets = {}

        for rank, item in enumerate(self.unique_frames):
            frame_idx = item['index']
            thumb_pil = item.get('thumbnail')
            qimg = pil_to_qimage(thumb_pil)
            pix = QPixmap.fromImage(qimg)

            # Container widget for each thumbnail
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet("""
                QFrame {
                    background: #fff;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 2px;
                }
                QFrame:hover {
                    border: 2px solid #2196F3;
                    background: #e3f2fd;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(2, 2, 2, 2)
            card_layout.setSpacing(2)

            # Image label
            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setPixmap(pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            card_layout.addWidget(img_lbl)

            # Frame label
            txt_lbl = QLabel(f"#{rank + 1} (F{frame_idx + 1})")
            txt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #555;")
            card_layout.addWidget(txt_lbl)

            # Connect click
            def make_click_handler(target_idx):
                return lambda event: self.load_frame(target_idx)

            card.mousePressEvent = make_click_handler(frame_idx)

            self.thumb_widgets[frame_idx] = card
            # Insert before the trailing stretch
            self.filmstrip_row.insertWidget(self.filmstrip_row.count() - 1, card)

    def highlight_filmstrip_thumbnail(self, frame_index):
        if not hasattr(self, 'thumb_widgets'):
            return

        for idx, card in self.thumb_widgets.items():
            if idx == frame_index:
                card.setStyleSheet("""
                    QFrame {
                        background: #e8f5e9;
                        border: 2px solid #2e7d32;
                        border-radius: 4px;
                        padding: 2px;
                    }
                """)
            else:
                card.setStyleSheet("""
                    QFrame {
                        background: #fff;
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        padding: 2px;
                    }
                    QFrame:hover {
                        border: 2px solid #2196F3;
                        background: #e3f2fd;
                    }
                """)

    # --- Export ---

    def export(self):
        if not self.current_file:
            QMessageBox.warning(self, "No Video", "Please drop or select a video or GIF to extract.")
            return

        # Determine target files
        if self.batch_check.isChecked() and len(self.valid_files) > 1:
            files_to_process = self.valid_files
        else:
            files_to_process = [self.current_file]

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        mode = self.mode_combo.currentData()
        threshold = self.threshold_spin.value()
        step = self.step_spin.value()
        output_format = self.format_combo.currentData()
        jpeg_quality = self.quality_spin.value()
        base_name = self.main_window.override_name_input.text()
        start_index = self.main_window.start_index_input.value()
        zero_pad = self.padding_combo.currentData()
        create_subfolder = self.subfolder_check.isChecked()

        self.extract_worker = FrameExtractWorkerThread(
            file_paths=files_to_process,
            output_dir=output_dir,
            mode=mode,
            threshold=threshold,
            step=step,
            output_format=output_format,
            jpeg_quality=jpeg_quality,
            base_name=base_name,
            start_index=start_index,
            zero_pad=zero_pad,
            create_subfolder=create_subfolder
        )

        self.extract_worker.progress.connect(self.update_export_status)
        self.extract_worker.finished.connect(self.on_export_finished)

        self.main_window.set_export_enabled(False)
        self.main_window.set_status("Starting frame extraction...")
        self.extract_worker.start()

    def update_export_status(self, message):
        self.main_window.set_status(message)

    def on_export_finished(self, success, message):
        self.main_window.set_export_enabled(True)
        self.main_window.set_status(message)

        if success:
            QMessageBox.information(self, "Export Complete", message)
        else:
            QMessageBox.critical(self, "Export Failed", f"An error occurred during extraction:\n{message}")
