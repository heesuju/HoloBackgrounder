import os
from PIL import Image
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QSpinBox, QCheckBox, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QFileDialog, QGroupBox, QFormLayout,
    QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QBrush

import pixel_art
from workers import PixelWorkerThread

class ResizableGraphicsView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene() and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

class PixelTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.valid_files = []
        self.current_preview_index = 0

        self.current_pil_img = None
        self.recommended_size = 64
        self.original_qimage = None
        self.processed_qimage = None
        self.current_pixel_dims = (0, 0)

        self._updating_ui = False
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(50)
        self.update_timer.timeout.connect(self.update_display)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Controls Section
        settings_group = QGroupBox("픽셀화 설정 (Pixel Art Settings)")
        settings_layout = QVBoxLayout()

        row1_layout = QHBoxLayout()

        # --- Pixel Size Section ---
        size_layout = QFormLayout()
        
        self.size_preset_combo = QComboBox()
        self.size_preset_combo.addItem("추천 (자동 계산)", "auto")
        self.size_preset_combo.addItem("16 x 16", 16)
        self.size_preset_combo.addItem("32 x 32", 32)
        self.size_preset_combo.addItem("48 x 48", 48)
        self.size_preset_combo.addItem("64 x 64", 64)
        self.size_preset_combo.addItem("96 x 96", 96)
        self.size_preset_combo.addItem("128 x 128", 128)
        self.size_preset_combo.addItem("192 x 192", 192)
        self.size_preset_combo.addItem("256 x 256", 256)
        self.size_preset_combo.addItem("원본 크기 (Original)", "original")
        self.size_preset_combo.addItem("직접 입력 (Custom)", "custom")
        self.size_preset_combo.currentIndexChanged.connect(self.on_size_preset_changed)

        self.size_spinbox = QSpinBox()
        self.size_spinbox.setRange(8, 4096)
        self.size_spinbox.setValue(64)
        self.size_spinbox.setSuffix(" px")
        self.size_spinbox.setToolTip("픽셀 아트의 최대 가로/세로 해상도를 지정합니다.")
        self.size_spinbox.valueChanged.connect(self.on_size_spinbox_changed)

        size_controls_layout = QHBoxLayout()
        size_controls_layout.addWidget(self.size_preset_combo, 2)
        size_controls_layout.addWidget(self.size_spinbox, 1)

        size_layout.addRow("픽셀 크기:", size_controls_layout)
        row1_layout.addLayout(size_layout, 1)

        # --- Color Quantization Section ---
        color_layout = QFormLayout()

        self.color_preset_combo = QComboBox()
        self.color_preset_combo.addItem("16 색상 (추천)", 16)
        self.color_preset_combo.addItem("4 색상 (Game Boy)", 4)
        self.color_preset_combo.addItem("8 색상 (3-bit)", 8)
        self.color_preset_combo.addItem("32 색상 (5-bit)", 32)
        self.color_preset_combo.addItem("64 색상 (6-bit)", 64)
        self.color_preset_combo.addItem("128 색상", 128)
        self.color_preset_combo.addItem("256 색상 (8-bit)", 256)
        self.color_preset_combo.addItem("원본 색상 (Original)", 0)
        self.color_preset_combo.addItem("직접 입력 (Custom)", "custom")
        self.color_preset_combo.currentIndexChanged.connect(self.on_color_preset_changed)

        self.color_spinbox = QSpinBox()
        self.color_spinbox.setRange(2, 256)
        self.color_spinbox.setValue(16)
        self.color_spinbox.setSuffix(" 색")
        self.color_spinbox.setToolTip("양자화할 팔레트 색상 수를 지정합니다 (2 ~ 256).")
        self.color_spinbox.valueChanged.connect(self.on_color_spinbox_changed)

        color_controls_layout = QHBoxLayout()
        color_controls_layout.addWidget(self.color_preset_combo, 2)
        color_controls_layout.addWidget(self.color_spinbox, 1)

        color_layout.addRow("색상 양자화:", color_controls_layout)
        row1_layout.addLayout(color_layout, 1)

        settings_layout.addLayout(row1_layout)

        # --- Row 2: Advanced Options & Export Scale ---
        row2_layout = QHBoxLayout()

        self.dither_check = QCheckBox("디더링 적용 (Floyd-Steinberg)")
        self.dither_check.setToolTip("색상 전환부에 레트로 디더링 패턴을 적용합니다.")
        self.dither_check.toggled.connect(self.schedule_update_display)
        row2_layout.addWidget(self.dither_check)

        self.crisp_alpha_check = QCheckBox("투명 배경 깔끔화 (Crisp Alpha)")
        self.crisp_alpha_check.setChecked(True)
        self.crisp_alpha_check.setToolTip("투명 PNG 스프라이트의 외곽선 번짐을 방지하고 깔끔한 픽셀 경계로 다듬습니다.")
        self.crisp_alpha_check.toggled.connect(self.schedule_update_display)
        row2_layout.addWidget(self.crisp_alpha_check)

        row2_layout.addStretch()

        scale_label = QLabel("출력 크기:")
        self.scale_combo = QComboBox()
        self.scale_combo.addItem("원본 해상도로 확대 (Nearest Neighbor)", "original")
        self.scale_combo.addItem("실제 픽셀 해상도 (1x 스프라이트)", "1x")
        self.scale_combo.addItem("2배 확대 (2x)", 2)
        self.scale_combo.addItem("4배 확대 (4x)", 4)
        self.scale_combo.addItem("8배 확대 (8x)", 8)
        self.scale_combo.setToolTip("내보낼 때 이미지를 원본 크기로 선명하게 확대할지, 실제 저해상도 픽셀 크기로 저장할지 선택합니다.")
        row2_layout.addWidget(scale_label)
        row2_layout.addWidget(self.scale_combo)

        settings_layout.addLayout(row2_layout)
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # 2. Preview Toolbar (Info & Nav & Compare)
        preview_toolbar = QHBoxLayout()

        self.prev_btn = QPushButton("◀ 이전")
        self.prev_btn.setFixedWidth(70)
        self.prev_btn.clicked.connect(self.prev_image)
        self.prev_btn.setEnabled(False)
        preview_toolbar.addWidget(self.prev_btn)

        self.next_btn = QPushButton("다음 ▶")
        self.next_btn.setFixedWidth(70)
        self.next_btn.clicked.connect(self.next_image)
        self.next_btn.setEnabled(False)
        preview_toolbar.addWidget(self.next_btn)

        self.preview_info_label = QLabel("이미지를 드래그 앤 드롭하세요")
        self.preview_info_label.setStyleSheet("font-weight: bold; color: #333;")
        preview_toolbar.addWidget(self.preview_info_label, 1)

        self.compare_btn = QPushButton("원본 보기 (Hold)")
        self.compare_btn.setFixedWidth(130)
        self.compare_btn.setToolTip("누르고 있는 동안 원본 이미지를 미리봅니다.")
        self.compare_btn.pressed.connect(self.show_original)
        self.compare_btn.released.connect(self.show_processed)
        self.compare_btn.setEnabled(False)
        preview_toolbar.addWidget(self.compare_btn)

        layout.addLayout(preview_toolbar)

        # 3. Graphics View with Checkerboard
        self.view = ResizableGraphicsView()
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        bg_pixmap = self.create_checkerboard_pattern()
        self.view.setBackgroundBrush(QBrush(bg_pixmap))
        layout.addWidget(self.view)

    def create_checkerboard_pattern(self):
        size = 16
        img = QImage(size * 2, size * 2, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        painter.fillRect(0, 0, size, size, QColor(225, 225, 225))
        painter.fillRect(size, size, size, size, QColor(225, 225, 225))
        painter.fillRect(size, 0, size, size, QColor(190, 190, 190))
        painter.fillRect(0, size, size, size, QColor(190, 190, 190))
        painter.end()
        return QPixmap.fromImage(img)

    def on_global_files_changed(self):
        self.valid_files = [
            f for f in self.main_window.current_files
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))
        ]
        self.current_preview_index = 0
        if self.valid_files:
            self.load_image_index(0)
            self.main_window.set_export_enabled(True)
        else:
            self.clear_image()
            self.main_window.set_export_enabled(False)

    def load_image_index(self, index):
        if not (0 <= index < len(self.valid_files)):
            self.clear_image()
            return

        self.current_preview_index = index
        file_path = self.valid_files[index]

        try:
            pil_img = Image.open(file_path)
            self.current_pil_img = pil_img.copy()

            # Cache original QImage for comparison
            disp_orig = self.current_pil_img.convert("RGBA")
            data = disp_orig.tobytes("raw", "RGBA")
            self.original_qimage = QImage(data, disp_orig.width, disp_orig.height, QImage.Format.Format_RGBA8888).copy()

            # Calculate recommended pixel size
            self.recommended_size = pixel_art.recommend_pixel_size(self.current_pil_img)
            self._updating_ui = True
            self.size_preset_combo.setItemText(0, f"추천 ({self.recommended_size}px)")

            # If current preset is "auto", update spinbox
            if self.size_preset_combo.currentData() == "auto":
                self.size_spinbox.setValue(self.recommended_size)
            elif self.size_preset_combo.currentData() == "original":
                self.size_spinbox.setValue(max(self.current_pil_img.width, self.current_pil_img.height))
            self._updating_ui = False

            # Update nav buttons
            self.prev_btn.setEnabled(self.current_preview_index > 0)
            self.next_btn.setEnabled(self.current_preview_index < len(self.valid_files) - 1)
            self.compare_btn.setEnabled(True)

            self.update_display()
        except Exception as e:
            QMessageBox.warning(self, "오류", f"이미지 로드 실패 ({os.path.basename(file_path)}): {e}")

    def prev_image(self):
        if self.current_preview_index > 0:
            self.load_image_index(self.current_preview_index - 1)

    def next_image(self):
        if self.current_preview_index < len(self.valid_files) - 1:
            self.load_image_index(self.current_preview_index + 1)

    def on_size_preset_changed(self, idx):
        if self._updating_ui or self.current_pil_img is None:
            return
        data = self.size_preset_combo.currentData()
        self._updating_ui = True
        if data == "auto":
            self.size_spinbox.setValue(self.recommended_size)
        elif isinstance(data, int):
            self.size_spinbox.setValue(data)
        elif data == "original":
            self.size_spinbox.setValue(max(self.current_pil_img.width, self.current_pil_img.height))
        self._updating_ui = False
        self.schedule_update_display()

    def on_size_spinbox_changed(self, val):
        if self._updating_ui:
            return
        # If value doesn't match current preset, change combo to custom
        data = self.size_preset_combo.currentData()
        if data == "auto" and val == self.recommended_size:
            pass
        elif isinstance(data, int) and val == data:
            pass
        elif data == "original" and self.current_pil_img and val == max(self.current_pil_img.width, self.current_pil_img.height):
            pass
        else:
            custom_idx = self.size_preset_combo.findData("custom")
            if custom_idx >= 0 and self.size_preset_combo.currentIndex() != custom_idx:
                self._updating_ui = True
                self.size_preset_combo.setCurrentIndex(custom_idx)
                self._updating_ui = False
        self.schedule_update_display()

    def on_color_preset_changed(self, idx):
        if self._updating_ui:
            return
        data = self.color_preset_combo.currentData()
        self._updating_ui = True
        if isinstance(data, int):
            if data == 0:
                self.color_spinbox.setEnabled(False)
            else:
                self.color_spinbox.setEnabled(True)
                self.color_spinbox.setValue(data)
        elif data == "custom":
            self.color_spinbox.setEnabled(True)
        self._updating_ui = False
        self.schedule_update_display()

    def on_color_spinbox_changed(self, val):
        if self._updating_ui:
            return
        data = self.color_preset_combo.currentData()
        if isinstance(data, int) and val == data:
            pass
        else:
            custom_idx = self.color_preset_combo.findData("custom")
            if custom_idx >= 0 and self.color_preset_combo.currentIndex() != custom_idx:
                self._updating_ui = True
                self.color_preset_combo.setCurrentIndex(custom_idx)
                self._updating_ui = False
        self.schedule_update_display()

    def schedule_update_display(self):
        self.update_timer.start()

    def update_display(self):
        if self.current_pil_img is None:
            return

        target_size = self.size_spinbox.value()
        size_preset = self.size_preset_combo.currentData()
        if size_preset == "original":
            target_size = 0

        color_preset = self.color_preset_combo.currentData()
        if color_preset == 0:
            num_colors = 0
        else:
            num_colors = self.color_spinbox.value()

        dither = self.dither_check.isChecked()
        crisp_alpha = self.crisp_alpha_check.isChecked()

        try:
            # Generate pixel art (preview always rendered scaled up for crisp display)
            result_img, pixel_dims = pixel_art.process_pixel_art(
                self.current_pil_img,
                target_pixel_size=target_size,
                num_colors=num_colors,
                dither=dither,
                crisp_alpha=crisp_alpha,
                output_scale="original"
            )

            self.current_pixel_dims = pixel_dims

            disp_img = result_img.convert("RGBA")
            data = disp_img.tobytes("raw", "RGBA")
            self.processed_qimage = QImage(data, disp_img.width, disp_img.height, QImage.Format.Format_RGBA8888).copy()

            self.scene.setSceneRect(0, 0, self.processed_qimage.width(), self.processed_qimage.height())
            self.pixmap_item.setPixmap(QPixmap.fromImage(self.processed_qimage))
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

            # Update info label
            orig_w, orig_h = self.current_pil_img.size
            pw, ph = pixel_dims
            ratio = max(1, round(max(orig_w, orig_h) / max(pw, ph)))
            cur_file = os.path.basename(self.valid_files[self.current_preview_index])
            color_text = f"{num_colors}색" if num_colors > 0 else "원본색"
            dither_text = " [디더링]" if dither else ""

            self.preview_info_label.setText(
                f"[{self.current_preview_index + 1}/{len(self.valid_files)}] {cur_file}  |  "
                f"원본: {orig_w}x{orig_h} ➔ 픽셀: {pw}x{ph} ({ratio}배 블록)  |  "
                f"{color_text}{dither_text}"
            )
        except Exception as e:
            self.preview_info_label.setText(f"변환 오류: {e}")

    def show_original(self):
        if self.original_qimage is not None:
            self.pixmap_item.setPixmap(QPixmap.fromImage(self.original_qimage))

    def show_processed(self):
        if self.processed_qimage is not None:
            self.pixmap_item.setPixmap(QPixmap.fromImage(self.processed_qimage))

    def clear_image(self):
        self.current_pil_img = None
        self.original_qimage = None
        self.processed_qimage = None
        self.pixmap_item.setPixmap(QPixmap())
        self.scene.setSceneRect(0, 0, 0, 0)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.compare_btn.setEnabled(False)
        self.preview_info_label.setText("이미지를 드래그 앤 드롭하세요")
        self.main_window.set_export_enabled(False)

    def export(self):
        if not self.valid_files or self.current_pil_img is None:
            return

        size_preset = self.size_preset_combo.currentData()
        if size_preset == "original":
            pixel_size = 0
        elif size_preset == "auto":
            pixel_size = "auto"
        else:
            pixel_size = self.size_spinbox.value()

        color_preset = self.color_preset_combo.currentData()
        num_colors = 0 if color_preset == 0 else self.color_spinbox.value()
        dither = self.dither_check.isChecked()
        crisp_alpha = self.crisp_alpha_check.isChecked()
        output_scale = self.scale_combo.currentData()

        override_name = self.main_window.override_name_input.text().strip()
        start_index = self.main_window.start_index_input.value()

        # Batch Export when multiple files are loaded
        if len(self.valid_files) > 1:
            output_dir = QFileDialog.getExistingDirectory(self, "변환된 픽셀 아트 저장 폴더 선택")
            if not output_dir:
                return

            self.worker = PixelWorkerThread(
                file_paths=self.valid_files,
                output_dir=output_dir,
                pixel_size=pixel_size,
                num_colors=num_colors,
                dither=dither,
                crisp_alpha=crisp_alpha,
                output_scale=output_scale,
                override_name=override_name,
                start_index=start_index
            )
            self.worker.progress.connect(self.main_window.set_status)
            self.worker.finished.connect(self.on_export_finished)

            self.main_window.set_export_enabled(False)
            self.main_window.set_status("픽셀 아트 일괄 변환 시작...")
            self.worker.start()

        # Single File Export
        else:
            cur_path = self.valid_files[0]
            ext = os.path.splitext(cur_path)[1]
            if ext.lower() not in ('.png', '.webp', '.jpg', '.jpeg', '.bmp'):
                ext = '.png'

            base = override_name if override_name else os.path.splitext(os.path.basename(cur_path))[0] + "_pixel"
            default_name = f"{base}{ext}"

            file_path, _ = QFileDialog.getSaveFileName(
                self, "픽셀 아트 저장", default_name, "PNG Images (*.png);;WebP Images (*.webp);;All Files (*)"
            )
            if not file_path:
                return

            self.main_window.set_status("픽셀 아트 변환 및 저장 중...")
            QApplication.processEvents()

            try:
                effective_size = pixel_art.recommend_pixel_size(self.current_pil_img) if pixel_size == "auto" else pixel_size
                result_img, _ = pixel_art.process_pixel_art(
                    self.current_pil_img,
                    target_pixel_size=effective_size,
                    num_colors=num_colors,
                    dither=dither,
                    crisp_alpha=crisp_alpha,
                    output_scale=output_scale
                )
                result_img.save(file_path)
                self.main_window.set_status(f"저장 완료: {file_path}")
                QMessageBox.information(self, "성공", f"성공적으로 저장되었습니다:\n{file_path}")
            except Exception as e:
                self.main_window.set_status(f"저장 실패: {e}")
                QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다:\n{e}")

    def on_export_finished(self, success, message):
        self.main_window.set_export_enabled(True)
        self.main_window.set_status(message)
        if success:
            QMessageBox.information(self, "성공", f"작업 완료!\n{message}")
        else:
            QMessageBox.critical(self, "오류", f"오류 발생:\n{message}")
