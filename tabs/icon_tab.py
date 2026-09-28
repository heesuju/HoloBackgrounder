import os
from PIL import Image
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QGroupBox,
    QMessageBox, QApplication, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QBrush

import icon_generator

class IconPreview(QFrame):
    def __init__(self, size, parent=None):
        super().__init__(parent)
        self.size = size

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.image_label = QLabel()
        self.image_label.setFixedSize(128, 128)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid #999;")
        self.image_label.setPixmap(self.create_checkerboard_pattern())
        layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.caption = QLabel(f"{size} x {size}")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.caption)

    def create_checkerboard_pattern(self):
        cell = 8
        img = QImage(128, 128, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        for y in range(0, 128, cell):
            for x in range(0, 128, cell):
                even = ((x // cell) + (y // cell)) % 2 == 0
                painter.fillRect(x, y, cell, cell, QColor(225, 225, 225) if even else QColor(190, 190, 190))
        painter.end()
        return QPixmap.fromImage(img)

    def set_image(self, pil_img):
        disp = pil_img.convert("RGBA")
        data = disp.tobytes("raw", "RGBA")
        qimg = QImage(data, disp.width, disp.height, QImage.Format.Format_RGBA8888).copy()
        pixmap = QPixmap.fromImage(qimg)

        # Show it at a consistent on-screen size, using nearest-neighbor for
        # small icons so pixels stay crisp instead of blurring.
        scaled = pixmap.scaled(
            112, 112, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )

        canvas = QPixmap(128, 128)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.drawPixmap(0, 0, self.create_checkerboard_pattern())
        x = (128 - scaled.width()) // 2
        y = (128 - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()
        self.image_label.setPixmap(canvas)

    def clear(self):
        self.image_label.setPixmap(self.create_checkerboard_pattern())


class IconTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.current_file = None
        self.current_pil_img = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info_group = QGroupBox("Icon Generator")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "Takes the first input image and generates 1:1 icon versions at "
            "16x16, 32x32, 48x48, and 128x128, using the highest-quality "
            "resampling. Transparency is preserved if the source image has an "
            "alpha channel."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)

        self.status_label = QLabel("이미지를 드래그 앤 드롭하세요")
        self.status_label.setStyleSheet("font-weight: bold; color: #333;")
        info_layout.addWidget(self.status_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        previews_layout = QHBoxLayout()
        previews_layout.addStretch()
        self.previews = {}
        for size in icon_generator.ICON_SIZES:
            preview = IconPreview(size)
            self.previews[size] = preview
            previews_layout.addWidget(preview)
        previews_layout.addStretch()
        layout.addLayout(previews_layout)

        layout.addStretch()

    def on_global_files_changed(self):
        valid_file = self.get_valid_file()
        if valid_file:
            self.load_image_from_path(valid_file)
        else:
            self.clear_image()

    def get_valid_file(self):
        for f in self.main_window.current_files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                return f
        return None

    def load_image_from_path(self, file_path):
        try:
            self.current_pil_img = Image.open(file_path)
            self.current_file = file_path

            icons, alpha = icon_generator.generate_icons(self.current_pil_img)
            for size, icon_img in icons.items():
                self.previews[size].set_image(icon_img)

            alpha_text = "투명 배경 유지" if alpha else "불투명 (알파 없음)"
            self.status_label.setText(
                f"{os.path.basename(file_path)} ({self.current_pil_img.width}x{self.current_pil_img.height}, {alpha_text})"
            )
            self.main_window.set_export_enabled(True)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"이미지 로드 실패 ({os.path.basename(file_path)}): {e}")

    def clear_image(self):
        self.current_pil_img = None
        self.current_file = None
        for preview in self.previews.values():
            preview.clear()
        self.status_label.setText("이미지를 드래그 앤 드롭하세요")
        self.main_window.set_export_enabled(False)

    def export(self):
        if self.current_pil_img is None:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "아이콘 저장 폴더 선택")
        if not output_dir:
            return

        override_name = self.main_window.override_name_input.text().strip()
        base = override_name if override_name else os.path.splitext(os.path.basename(self.current_file))[0]

        self.main_window.set_status("아이콘 생성 중...")
        QApplication.processEvents()

        try:
            icons, _ = icon_generator.generate_icons(self.current_pil_img)
            saved = []
            for size, icon_img in icons.items():
                out_path = os.path.join(output_dir, f"{base}_{size}.png")
                icon_img.save(out_path, "PNG")
                saved.append(out_path)

            self.main_window.set_status(f"{len(saved)}개 아이콘 저장 완료: {output_dir}")
            QMessageBox.information(self, "성공", "다음 파일이 저장되었습니다:\n" + "\n".join(saved))
        except Exception as e:
            self.main_window.set_status(f"저장 실패: {e}")
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다:\n{e}")
