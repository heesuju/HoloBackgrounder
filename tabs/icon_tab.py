import os
from PIL import Image
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFileDialog, QGroupBox, QMessageBox, QApplication,
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsSimpleTextItem
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPixmap, QPen, QColor, QBrush, QFont

import icon_generator
from components import ZoomableGraphicsView, checkerboard_pixmap

CELL = 128        # on-screen box each icon is drawn into (scene units)
GAP = 24
CAPTION_H = 24


def pil_to_pixmap(img):
    disp = img.convert("RGBA")
    data = disp.tobytes("raw", "RGBA")
    qimg = QImage(data, disp.width, disp.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


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

        layout.addStretch()

        # Preview (shown in the main window's preview panel): each icon is
        # drawn into a CELL x CELL box with nearest-neighbor scaling so pixels stay crisp
        self.view = ZoomableGraphicsView(pan_with_left=True)
        self.view.setBackgroundBrush(QBrush(QColor(245, 245, 245)))
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)
        self.preview_widget = self.view

        checker = QBrush(checkerboard_pixmap(8, QColor(225, 225, 225), QColor(190, 190, 190)))
        border = QPen(QColor(153, 153, 153))
        border.setCosmetic(True)
        caption_font = QFont()
        caption_font.setBold(True)

        self.icon_items = {}
        x = 0
        for size in icon_generator.ICON_SIZES:
            bg = QGraphicsRectItem(x, 0, CELL, CELL)
            bg.setBrush(checker)
            bg.setPen(border)
            self.scene.addItem(bg)

            item = QGraphicsPixmapItem()
            item.setTransformationMode(Qt.TransformationMode.FastTransformation)
            item.setPos(x, 0)
            item.setScale(CELL / size)
            self.scene.addItem(item)
            self.icon_items[size] = item

            caption = QGraphicsSimpleTextItem(f"{size} x {size}")
            caption.setFont(caption_font)
            caption.setPos(x + (CELL - caption.boundingRect().width()) / 2, CELL + 4)
            self.scene.addItem(caption)
            x += CELL + GAP

        self.scene.setSceneRect(QRectF(-GAP / 2, -GAP / 2, x, CELL + CAPTION_H + GAP))

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
                self.icon_items[size].setPixmap(pil_to_pixmap(icon_img))
            self.view.fit_view()

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
        for item in self.icon_items.values():
            item.setPixmap(QPixmap())
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
