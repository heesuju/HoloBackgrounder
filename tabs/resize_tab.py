import os
from PIL import Image
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QGroupBox,
    QFormLayout, QComboBox, QSpinBox, QCheckBox, QMessageBox, QApplication
)

import image_resizer


class ResizeTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.valid_files = []
        self.src_size = None
        self._driver = "width"
        self._updating_ui = False

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info_group = QGroupBox("Lossless Resize")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "이미지를 최대한 손실 없이 리사이즈하여 PNG로 저장합니다. "
            "색상 모드, 투명도, ICC 프로파일, DPI를 유지하며 PNG는 무손실 압축됩니다. "
            "픽셀 아트는 'Nearest' 필터를 사용하세요."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)

        self.status_label = QLabel("이미지를 드래그 앤 드롭하세요")
        self.status_label.setStyleSheet("font-weight: bold; color: #333;")
        info_layout.addWidget(self.status_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        settings_group = QGroupBox("리사이즈 설정")
        form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("크기 지정 (px)", "pixels")
        self.mode_combo.addItem("비율 (%)", "percent")
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        form.addRow("방식:", self.mode_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 32768)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(lambda v: self.on_dim_changed("width", v))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 32768)
        self.height_spin.setSuffix(" px")
        self.height_spin.valueChanged.connect(lambda v: self.on_dim_changed("height", v))
        dims_layout = QHBoxLayout()
        dims_layout.addWidget(QLabel("가로"))
        dims_layout.addWidget(self.width_spin)
        dims_layout.addWidget(QLabel("세로"))
        dims_layout.addWidget(self.height_spin)
        form.addRow("크기:", dims_layout)

        self.keep_aspect_check = QCheckBox("가로세로 비율 유지")
        self.keep_aspect_check.setChecked(True)
        self.keep_aspect_check.toggled.connect(self.update_info)
        form.addRow("", self.keep_aspect_check)

        self.percent_spin = QSpinBox()
        self.percent_spin.setRange(1, 1000)
        self.percent_spin.setValue(50)
        self.percent_spin.setSuffix(" %")
        self.percent_spin.valueChanged.connect(self.update_info)
        form.addRow("비율:", self.percent_spin)

        self.resample_combo = QComboBox()
        self.resample_combo.addItem("Lanczos (최고 품질, 기본)", "lanczos")
        self.resample_combo.addItem("Bicubic", "bicubic")
        self.resample_combo.addItem("Nearest (픽셀 아트 / 정수 배율 무손실)", "nearest")
        form.addRow("필터:", self.resample_combo)

        settings_group.setLayout(form)
        layout.addWidget(settings_group)

        self.result_label = QLabel("")
        layout.addWidget(self.result_label)
        layout.addStretch()

        self.on_mode_changed()

    def on_mode_changed(self):
        pixels = self.mode_combo.currentData() == "pixels"
        self.width_spin.setEnabled(pixels)
        self.height_spin.setEnabled(pixels)
        self.keep_aspect_check.setEnabled(pixels)
        self.percent_spin.setEnabled(not pixels)
        self.update_info()

    def on_dim_changed(self, which, value):
        if self._updating_ui or self.src_size is None:
            return
        self._driver = which
        if self.keep_aspect_check.isChecked():
            sw, sh = self.src_size
            self._updating_ui = True
            if which == "width":
                self.height_spin.setValue(max(1, round(sh * value / sw)))
            else:
                self.width_spin.setValue(max(1, round(sw * value / sh)))
            self._updating_ui = False
        self.update_info()

    def current_target(self, src_size):
        return image_resizer.compute_size(
            src_size,
            self.mode_combo.currentData(),
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            percent=self.percent_spin.value(),
            keep_aspect=self.keep_aspect_check.isChecked(),
            driver=self._driver,
        )

    def update_info(self):
        if self.src_size is None:
            self.result_label.setText("")
            return
        w, h = self.current_target(self.src_size)
        self.result_label.setText(f"출력 크기 (첫 번째 이미지 기준): {self.src_size[0]}x{self.src_size[1]} ➔ {w}x{h}")

    # --- file handling ---
    def on_global_files_changed(self):
        self.valid_files = [
            f for f in self.main_window.current_files
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'))
        ]
        if not self.valid_files:
            self.src_size = None
            self.status_label.setText("이미지를 드래그 앤 드롭하세요")
            self.result_label.setText("")
            self.main_window.set_export_enabled(False)
            return

        try:
            with Image.open(self.valid_files[0]) as img:
                size = img.size
        except Exception as e:
            QMessageBox.warning(self, "오류", f"이미지 로드 실패 ({os.path.basename(self.valid_files[0])}): {e}")
            return

        self.src_size = size
        self._updating_ui = True
        self.width_spin.setValue(size[0])
        self.height_spin.setValue(size[1])
        self._updating_ui = False
        self._driver = "width"

        self.status_label.setText(
            f"{os.path.basename(self.valid_files[0])} ({size[0]}x{size[1]})"
            + (f" 외 {len(self.valid_files) - 1}개" if len(self.valid_files) > 1 else "")
        )
        self.update_info()
        self.main_window.set_export_enabled(True)

    def render(self, path):
        with Image.open(path) as img:
            img.load()
            target = self.current_target(img.size)
            return image_resizer.resize_image(img, target, self.resample_combo.currentData())

    # --- export ---
    def export(self):
        if not self.valid_files:
            return

        override_name = self.main_window.override_name_input.text().strip()
        start_index = self.main_window.start_index_input.value()

        try:
            if len(self.valid_files) == 1:
                path = self.valid_files[0]
                out = self.render(path)
                base = override_name or os.path.splitext(os.path.basename(path))[0]
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "리사이즈 이미지 저장", f"{base}_{out.width}x{out.height}.png", "PNG Images (*.png)"
                )
                if not file_path:
                    return
                image_resizer.save_png(out, file_path)
                self.main_window.set_status(f"저장 완료: {file_path}")
                QMessageBox.information(self, "성공", f"성공적으로 저장되었습니다:\n{file_path}")
                return

            output_dir = QFileDialog.getExistingDirectory(self, "리사이즈 이미지 저장 폴더 선택")
            if not output_dir:
                return

            total = len(self.valid_files)
            for i, path in enumerate(self.valid_files):
                self.main_window.set_status(f"리사이즈 중... ({i + 1}/{total})")
                QApplication.processEvents()
                out = self.render(path)
                if override_name:
                    name = f"{override_name}_{start_index + i}"
                else:
                    name = f"{os.path.splitext(os.path.basename(path))[0]}_{out.width}x{out.height}"
                image_resizer.save_png(out, os.path.join(output_dir, f"{name}.png"))

            self.main_window.set_status(f"{total}개 이미지 저장 완료: {output_dir}")
            QMessageBox.information(self, "성공", f"{total}개 이미지가 저장되었습니다:\n{output_dir}")
        except Exception as e:
            self.main_window.set_status(f"저장 실패: {e}")
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다:\n{e}")
