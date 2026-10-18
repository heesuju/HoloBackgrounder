import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QGroupBox,
    QFormLayout, QComboBox, QSpinBox, QCheckBox, QMessageBox, QApplication,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem
)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush

from components import DragDropLabel, ZoomableGraphicsView
import image_resizer
import region_swap

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff')
PREVIEW_PATCH = 512  # replacement preview is rendered once at this size, then scaled


def pil_to_pixmap(img):
    disp = img.convert("RGBA")
    data = disp.tobytes("raw", "RGBA")
    qimg = QImage(data, disp.width, disp.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def checkerboard_pixmap(size=20):
    img = QImage(size * 2, size * 2, QImage.Format.Format_RGB32)
    painter = QPainter(img)
    painter.fillRect(0, 0, size * 2, size * 2, QColor(150, 150, 150))
    painter.fillRect(0, 0, size, size, QColor(200, 200, 200))
    painter.fillRect(size, size, size, size, QColor(200, 200, 200))
    painter.end()
    return QPixmap.fromImage(img)


class SquareRegionItem(QGraphicsRectItem):
    """A square selection that can be moved, or resized from its corners while
    staying 1:1. Coordinates are snapped to whole image pixels."""

    CORNERS = ('tl', 'tr', 'bl', 'br')

    def __init__(self, scene):
        super().__init__()
        self.scene_ref = scene
        self.setAcceptHoverEvents(True)
        pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(255, 0, 0, 40)))
        self.setZValue(3)

        self.active_handle = None
        self.anchor = None
        self.drag_offset = None

    def handle_size(self):
        # Keep handles ~10 screen px regardless of zoom
        views = self.scene_ref.views()
        scale = views[0].transform().m11() if views else 1.0
        return 10 / scale if scale > 0 else 10

    def handle_rects(self):
        r = self.rect()
        s = self.handle_size()
        pts = {'tl': r.topLeft(), 'tr': r.topRight(), 'bl': r.bottomLeft(), 'br': r.bottomRight()}
        return {k: QRectF(p.x() - s / 2, p.y() - s / 2, s, s) for k, p in pts.items()}

    def get_handle_at(self, pos):
        for k, hr in self.handle_rects().items():
            if hr.contains(pos):
                return k
        return None

    def boundingRect(self):
        s = self.handle_size()
        return self.rect().adjusted(-s, -s, s, s)

    def shape(self):
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.rect().isEmpty():
            return
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        pen = QPen(QColor(0, 0, 0))
        pen.setCosmetic(True)
        painter.setPen(pen)
        for hr in self.handle_rects().values():
            painter.drawRect(hr)

    def hoverMoveEvent(self, event):
        handle = self.get_handle_at(event.pos())
        if handle in ('tl', 'br'):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ('tr', 'bl'):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif self.rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        r = self.rect()
        self.active_handle = self.get_handle_at(event.pos())
        if self.active_handle:
            # Anchor at the opposite corner
            opposite = {'tl': r.bottomRight(), 'tr': r.bottomLeft(),
                        'bl': r.topRight(), 'br': r.topLeft()}
            self.anchor = opposite[self.active_handle]
            event.accept()
        elif r.contains(event.pos()):
            self.drag_offset = event.pos() - r.topLeft()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self.active_handle:
            self.scene_ref.set_square_from_drag(self.anchor, event.pos())
            event.accept()
        elif self.drag_offset is not None:
            r = self.rect()
            top_left = event.pos() - self.drag_offset
            self.scene_ref.set_region(round(top_left.x()), round(top_left.y()), round(r.width()))
            event.accept()

    def mouseReleaseEvent(self, event):
        self.active_handle = None
        self.anchor = None
        self.drag_offset = None
        event.accept()


class RegionScene(QGraphicsScene):
    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.drag_start = None

        self.pixmap_item = QGraphicsPixmapItem()
        self.pixmap_item.setZValue(0)
        self.addItem(self.pixmap_item)

        # Shown under the replacement preview so overwritten transparency is visible
        self.patch_bg_item = QGraphicsRectItem()
        self.patch_bg_item.setPen(QPen(Qt.PenStyle.NoPen))
        self.patch_bg_item.setBrush(QBrush(checkerboard_pixmap(8)))
        self.patch_bg_item.setZValue(1)
        self.addItem(self.patch_bg_item)
        self.patch_bg_item.hide()

        self.patch_item = QGraphicsPixmapItem()
        self.patch_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.patch_item.setZValue(2)
        self.addItem(self.patch_item)
        self.patch_item.hide()

        self.rect_item = SquareRegionItem(self)
        self.addItem(self.rect_item)
        self.rect_item.hide()

    def image_size(self):
        r = self.sceneRect()
        return int(r.width()), int(r.height())

    def set_region(self, x, y, size):
        w, h = self.image_size()
        if w <= 0 or h <= 0:
            return
        x, y, size = region_swap.clamp_region((w, h), x, y, size)
        self.rect_item.setRect(QRectF(x, y, size, size))
        self.rect_item.show()
        self.update_patch_preview()
        self.tab.on_region_changed(x, y, size)

    def set_square_from_drag(self, anchor, pos):
        """Square from a fixed anchor corner toward pos, limited to the image."""
        w, h = self.image_size()
        ax, ay = round(anchor.x()), round(anchor.y())
        dx, dy = pos.x() - ax, pos.y() - ay
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        room_x = (w - ax) if sx > 0 else ax
        room_y = (h - ay) if sy > 0 else ay
        size = max(1, min(round(max(abs(dx), abs(dy))), room_x, room_y))
        x = ax if sx > 0 else ax - size
        y = ay if sy > 0 else ay - size
        self.set_region(x, y, size)

    def update_patch_preview(self):
        pix = self.tab.patch_preview
        if pix is None or not self.rect_item.isVisible():
            self.patch_item.hide()
            self.patch_bg_item.hide()
            return
        r = self.rect_item.rect()
        self.patch_item.setPixmap(pix)
        self.patch_item.setScale(r.width() / pix.width())
        self.patch_item.setPos(r.topLeft())
        self.patch_item.show()
        self.patch_bg_item.setRect(r)
        self.patch_bg_item.setVisible(not self.tab.blend_check.isChecked())

    def mousePressEvent(self, event):
        if self.tab.base_img is None:
            return
        super().mousePressEvent(event)
        if event.isAccepted() and (self.rect_item.active_handle or self.rect_item.drag_offset is not None):
            return
        # Start a new square from the click point
        w, h = self.image_size()
        p = event.scenePos()
        self.drag_start = QPointF(max(0, min(round(p.x()), w)), max(0, min(round(p.y()), h)))
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            self.set_square_from_drag(self.drag_start, event.scenePos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_start = None
        super().mouseReleaseEvent(event)


class RegionTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.valid_files = []
        self.base_img = None
        self.replacement_path = None
        self.replacement_img = None
        self.patch_preview = None
        self._updating_ui = False

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info_group = QGroupBox("정사각형 영역 추출 / 교체")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "미리보기에서 드래그하여 1:1 영역을 지정하세요 (모서리로 크기 조절, 내부를 드래그하여 이동). "
            "교체 이미지가 없으면 해당 영역을 같은 픽셀 크기로 추출하고, "
            "교체 이미지를 넣으면 영역 크기에 맞춰 리사이즈하여 원본의 같은 위치에 덮어씁니다. "
            "여러 파일을 넣으면 같은 위치가 모든 파일에 적용됩니다."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        self.status_label = QLabel("이미지를 드래그 앤 드롭하세요")
        self.status_label.setStyleSheet("font-weight: bold; color: #333;")
        info_layout.addWidget(self.status_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Preview (shown in the main window's preview panel)
        self.view = ZoomableGraphicsView()
        self.view.setMouseTracking(True)
        self.view.setBackgroundBrush(QBrush(checkerboard_pixmap()))
        self.scene = RegionScene(self)
        self.view.setScene(self.scene)
        self.preview_widget = self.view

        # Region
        region_group = QGroupBox("영역 (px)")
        region_layout = QHBoxLayout()
        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        self.size_spin = QSpinBox()
        for label, spin in (("X", self.x_spin), ("Y", self.y_spin), ("크기", self.size_spin)):
            spin.setRange(0, 0)
            spin.valueChanged.connect(self.on_spin_changed)
            region_layout.addWidget(QLabel(label))
            region_layout.addWidget(spin, 1)
        self.size_spin.setSuffix(" px")
        region_group.setLayout(region_layout)
        layout.addWidget(region_group)

        # Replacement
        replace_group = QGroupBox("교체 이미지 (선택)")
        replace_layout = QVBoxLayout()
        row = QHBoxLayout()
        self.replace_drop = DragDropLabel(text="교체할 이미지를 여기에 드롭", file_types=list(IMAGE_EXTS))
        self.replace_drop.setFixedHeight(60)
        self.replace_drop.fileDropped.connect(self.set_replacement)
        row.addWidget(self.replace_drop, 1)
        btn_col = QVBoxLayout()
        browse_btn = QPushButton("찾아보기")
        browse_btn.clicked.connect(self.browse_replacement)
        btn_col.addWidget(browse_btn)
        self.clear_replace_btn = QPushButton("제거")
        self.clear_replace_btn.clicked.connect(self.clear_replacement)
        self.clear_replace_btn.setEnabled(False)
        btn_col.addWidget(self.clear_replace_btn)
        row.addLayout(btn_col)
        replace_layout.addLayout(row)

        form = QFormLayout()
        self.fit_combo = QComboBox()
        self.fit_combo.addItem("채우기 (중앙 크롭)", "cover")
        self.fit_combo.addItem("늘리기 (비율 무시)", "stretch")
        self.fit_combo.addItem("맞추기 (투명 여백)", "contain")
        self.fit_combo.currentIndexChanged.connect(self.refresh_patch_preview)
        form.addRow("비율이 다를 때:", self.fit_combo)

        self.resample_combo = QComboBox()
        self.resample_combo.addItem("Lanczos (최고 품질, 기본)", "lanczos")
        self.resample_combo.addItem("Bicubic", "bicubic")
        self.resample_combo.addItem("Nearest (픽셀 아트)", "nearest")
        self.resample_combo.currentIndexChanged.connect(self.refresh_patch_preview)
        form.addRow("필터:", self.resample_combo)

        self.blend_check = QCheckBox("투명한 부분은 원본 유지 (알파 합성)")
        self.blend_check.setToolTip("끄면 투명도까지 포함해 영역의 픽셀을 그대로 덮어씁니다.")
        self.blend_check.toggled.connect(self.scene.update_patch_preview)
        form.addRow("", self.blend_check)
        replace_layout.addLayout(form)
        replace_group.setLayout(replace_layout)
        layout.addWidget(replace_group)

        self.result_label = QLabel("")
        layout.addWidget(self.result_label)
        layout.addStretch()

    # --- region sync ---
    def current_region(self):
        return self.x_spin.value(), self.y_spin.value(), self.size_spin.value()

    def on_region_changed(self, x, y, size):
        """Called by the scene when the square moves; mirror it in the spinboxes."""
        self._updating_ui = True
        w, h = self.base_img.size
        self.size_spin.setRange(1, min(w, h))
        self.size_spin.setValue(size)
        self.x_spin.setRange(0, w - size)
        self.y_spin.setRange(0, h - size)
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self._updating_ui = False
        self.update_result_label()

    def on_spin_changed(self):
        if self._updating_ui or self.base_img is None:
            return
        self.scene.set_region(*self.current_region())

    def update_result_label(self):
        if self.base_img is None:
            self.result_label.setText("")
            return
        x, y, size = self.current_region()
        if self.replacement_img is not None:
            self.result_label.setText(
                f"교체: {os.path.basename(self.replacement_path)} "
                f"({self.replacement_img.width}x{self.replacement_img.height}) ➔ {size}x{size} @ ({x}, {y})"
            )
        else:
            self.result_label.setText(f"추출: ({x}, {y}) 에서 {size}x{size} px")

    # --- replacement ---
    def browse_replacement(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "교체 이미지 선택", "", "Images (" + " ".join("*" + e for e in IMAGE_EXTS) + ")"
        )
        if path:
            self.set_replacement(path)

    def set_replacement(self, path):
        try:
            img = region_swap.load_image(path)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"교체 이미지 로드 실패: {e}")
            return
        self.replacement_path = path
        self.replacement_img = img
        self.replace_drop.setText(f"{os.path.basename(path)}\n({img.width}x{img.height})")
        self.clear_replace_btn.setEnabled(True)
        self.refresh_patch_preview()

    def clear_replacement(self):
        self.replacement_path = None
        self.replacement_img = None
        self.replace_drop.setText("교체할 이미지를 여기에 드롭")
        self.clear_replace_btn.setEnabled(False)
        self.refresh_patch_preview()

    def refresh_patch_preview(self):
        if self.replacement_img is None:
            self.patch_preview = None
        else:
            patch = region_swap.fit_square(
                self.replacement_img, PREVIEW_PATCH,
                self.fit_combo.currentData(), self.resample_combo.currentData()
            )
            self.patch_preview = pil_to_pixmap(patch)
        self.scene.update_patch_preview()
        self.update_result_label()

    # --- file handling ---
    def on_global_files_changed(self):
        self.valid_files = [f for f in self.main_window.current_files if f.lower().endswith(IMAGE_EXTS)]
        if not self.valid_files:
            self.clear_image()
            return

        try:
            img = region_swap.load_image(self.valid_files[0])
        except Exception as e:
            QMessageBox.warning(self, "오류", f"이미지 로드 실패 ({os.path.basename(self.valid_files[0])}): {e}")
            self.clear_image()
            return

        prev_region = self.current_region() if self.base_img is not None else None
        self.base_img = img
        w, h = img.size
        self.scene.setSceneRect(0, 0, w, h)
        self.scene.pixmap_item.setPixmap(pil_to_pixmap(img))
        self.view.fit_view()

        if prev_region is None:
            # Default: largest centered square
            size = min(w, h)
            prev_region = ((w - size) // 2, (h - size) // 2, size)
        self.scene.set_region(*prev_region)

        self.status_label.setText(
            f"{os.path.basename(self.valid_files[0])} ({w}x{h})"
            + (f" 외 {len(self.valid_files) - 1}개" if len(self.valid_files) > 1 else "")
        )
        self.main_window.set_export_enabled(True)

    def clear_image(self):
        self.base_img = None
        self.scene.pixmap_item.setPixmap(QPixmap())
        self.scene.rect_item.hide()
        self.scene.update_patch_preview()
        self.scene.setSceneRect(0, 0, 0, 0)
        self.status_label.setText("이미지를 드래그 앤 드롭하세요")
        self.result_label.setText("")
        self.main_window.set_export_enabled(False)

    def render(self, path):
        img = region_swap.load_image(path)
        x, y, size = self.current_region()
        if self.replacement_img is None:
            return region_swap.extract_region(img, x, y, size)
        return region_swap.replace_region(
            img, self.replacement_img, x, y, size,
            fit=self.fit_combo.currentData(),
            resample=self.resample_combo.currentData(),
            blend=self.blend_check.isChecked(),
        )

    # --- export ---
    def export(self):
        if not self.valid_files or self.base_img is None:
            return

        override_name = self.main_window.override_name_input.text().strip()
        start_index = self.main_window.start_index_input.value()
        suffix = "replaced" if self.replacement_img is not None else "region"

        try:
            if len(self.valid_files) == 1:
                path = self.valid_files[0]
                out = self.render(path)
                base = override_name or f"{os.path.splitext(os.path.basename(path))[0]}_{suffix}"
                file_path, _ = QFileDialog.getSaveFileName(self, "이미지 저장", f"{base}.png", "PNG Images (*.png)")
                if not file_path:
                    return
                image_resizer.save_png(out, file_path)
                self.main_window.set_status(f"저장 완료: {file_path}")
                QMessageBox.information(self, "성공", f"성공적으로 저장되었습니다:\n{file_path}")
                return

            output_dir = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
            if not output_dir:
                return

            total = len(self.valid_files)
            for i, path in enumerate(self.valid_files):
                self.main_window.set_status(f"처리 중... ({i + 1}/{total})")
                QApplication.processEvents()
                out = self.render(path)
                if override_name:
                    name = f"{override_name}_{start_index + i}"
                else:
                    name = f"{os.path.splitext(os.path.basename(path))[0]}_{suffix}"
                image_resizer.save_png(out, os.path.join(output_dir, f"{name}.png"))

            self.main_window.set_status(f"{total}개 이미지 저장 완료: {output_dir}")
            QMessageBox.information(self, "성공", f"{total}개 이미지가 저장되었습니다:\n{output_dir}")
        except Exception as e:
            self.main_window.set_status(f"저장 실패: {e}")
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다:\n{e}")
