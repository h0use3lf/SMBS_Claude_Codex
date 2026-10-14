"""ROI 폴리곤 크롭 도구: 폴리곤 ROI + ROI별 Gray/HSV 필터 + 수동 라벨/카테고리 저장."""
import csv
import gc
import re
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import tifffile
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QKeySequence, QPainterPath, QPen, QPixmap, QPolygonF, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider, QVBoxLayout,
                               QWidget)

EXTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}
PROXY = 1600  # 축소 미리보기 계산용 크기(긴 변)
NATIVE_MAX = 6_000_000  # 화면에 보이는 영역이 이 픽셀 수 이하면 원본 1픽셀 단위로 미리보기
SLIDERS = ["Gray 최소", "Gray 최대", "H 최소", "H 최대", "S 최소", "S 최대", "V 최소", "V 최대"]
LIMITS = [255, 255, 179, 179, 255, 255, 255, 255]
DEFAULT = [0, 255, 0, 179, 0, 255, 0, 255]  # 전체 범위 = 필터 없음


def read_raw(path):
    """원본 비트깊이/채널을 그대로 읽어 RGB(A) 또는 2D로 반환 (EXIF 회전·색변환 없음)."""
    if Path(path).suffix.lower() in (".tif", ".tiff"):
        with tifffile.TiffFile(path) as t:
            a = t.pages[0].asarray()
        if a.ndim == 3 and a.shape[0] <= 4 < a.shape[2]:  # planar (C,H,W)
            a = np.moveaxis(a, 0, -1)
    else:
        a = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
        if a is None:
            raise ValueError("읽을 수 없는 이미지 파일")
        if a.ndim == 3:  # BGR(A) -> RGB(A)
            a = a[..., [2, 1, 0, 3][:a.shape[2]]]
    if a.ndim == 2:
        a = np.stack([a] * 3, -1)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError(f"지원하지 않는 형태: {a.shape}")
    return a


class Img:
    """원본 배열(rgb, alpha) + 화면용 QPixmap + 미리보기용 축소본(p8). 전체 크기 8비트 사본은 보관하지 않음."""

    def __init__(self, path):
        a = read_raw(path)
        self.rgb = np.ascontiguousarray(a[..., :3])
        self.alpha = np.ascontiguousarray(a[..., 3]) if a.shape[2] == 4 else None
        del a
        self.h, self.w = self.rgb.shape[:2]
        self.lo, self.hi = (0, 255) if self.rgb.dtype == np.uint8 else (float(self.rgb.min()), float(self.rgb.max()))
        d8 = self.to8(self.rgb)
        self.pix = QPixmap.fromImage(QImage(d8.data, self.w, self.h, self.w * 3, QImage.Format_RGB888))
        self.scale = min(1.0, PROXY / max(self.h, self.w))
        self.p8 = cv2.resize(d8, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA) if self.scale < 1 else d8

    def to8(self, a):
        if a.dtype == np.uint8:
            return a
        k = 255 / max(self.hi - self.lo, 1e-9)
        return cv2.convertScaleAbs(a, alpha=k, beta=-self.lo * k)


def keep_mask(rgb8, f):
    """f = [gmin,gmax,hmin,hmax,smin,smax,vmin,vmax]; 범위 안의 픽셀만 255."""
    m = cv2.inRange(cv2.cvtColor(rgb8, cv2.COLOR_RGB2GRAY), f[0], f[1])
    # shortcut: Hue 랩어라운드(빨강 등) 미지원, 필요 시 두 구간 OR로 확장
    return m & cv2.inRange(cv2.cvtColor(rgb8, cv2.COLOR_RGB2HSV), (f[2], f[4], f[6]), (f[3], f[5], f[7]))


def extract(im, pts, f, transparent):
    """폴리곤 bbox를 원본 해상도로 잘라 필터 적용. 반환: (RGB/RGBA 배열, 유지된 픽셀 수, bbox 좌상단)."""
    x0, y0 = np.floor(pts.min(0)).astype(int).clip(0)
    x1, y1 = np.minimum(np.ceil(pts.max(0)).astype(int), (im.w, im.h))
    sub = im.rgb[y0:y1, x0:x1]
    m = np.zeros(sub.shape[:2], np.uint8)
    cv2.fillPoly(m, [np.round(pts - (x0, y0)).astype(np.int32)], 255)
    m &= keep_mask(im.to8(sub), f)
    keep, n = m > 0, cv2.countNonZero(m)
    if not transparent:
        return sub * keep[..., None], n, (x0, y0)
    top = np.iinfo(sub.dtype).max if sub.dtype.kind in "ui" else 1.0
    a = im.alpha[y0:y1, x0:x1] if im.alpha is not None else np.full(m.shape, top, sub.dtype)
    return np.dstack([sub, a * keep]), n, (x0, y0)


CSV_COLS = ["saved_at", "source", "file", "category", "label", "kept_px", "roi_area_px",
            "bbox_x", "bbox_y", "bbox_w", "bbox_h", "gray_min", "gray_max", "h_min", "h_max",
            "s_min", "s_max", "v_min", "v_max", "points"]


def update_csv(path, rows):
    """이미지별 CSV에 행을 반영. 같은 출력 파일명 행은 새 값으로 교체(재저장 시 중복 방지)."""
    old = []
    if path.exists():
        with open(path, newline="", encoding="utf-8-sig") as fh:
            old = list(csv.DictReader(fh))
    new = {r["file"] for r in rows}
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # utf-8-sig: 엑셀에서 한글 깨짐 방지
        w = csv.DictWriter(fh, CSV_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows([r for r in old if r.get("file") not in new] + rows)


def write_img(dst, a):
    if dst.suffix == ".png":
        ok, buf = cv2.imencode(".png", cv2.cvtColor(a, cv2.COLOR_RGBA2BGRA if a.shape[2] == 4 else cv2.COLOR_RGB2BGR))
        if not ok:
            raise OSError("PNG 인코딩 실패")
        buf.tofile(str(dst))
    else:
        tifffile.imwrite(dst, a, photometric="rgb", extrasamples=(2,) if a.shape[2] == 4 else None, compression="zlib")


class NoWheelSlider(QSlider):
    def wheelEvent(self, e):
        e.ignore()  # 부모(스크롤 영역)로 전달


class NoWheelCombo(QComboBox):
    def wheelEvent(self, e):
        e.ignore()


class View(QGraphicsView):
    """휠=확대/축소(커서 기준), 우클릭/휠클릭 드래그=이동, 좌클릭=꼭짓점, 더블클릭=ROI 닫기."""

    def __init__(self, win):
        super().__init__(win.scene)
        self.win, self._pan = win, None
        self.setAcceptDrops(False)  # 드롭은 메인 창이 처리
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(40, 40, 40))

    def wheelEvent(self, e):
        k = 1.25 if e.angleDelta().y() > 0 else 0.8
        if 0.02 < self.transform().m11() * k < 64:
            self.scale(k, k)
            self.win.on_zoom()

    def mousePressEvent(self, e):
        if e.button() in (Qt.RightButton, Qt.MiddleButton):
            self._pan = e.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        elif e.button() == Qt.LeftButton:
            self.win.click(self.mapToScene(e.position().toPoint()))

    def mouseMoveEvent(self, e):
        p = e.position().toPoint()
        if self._pan is None:
            self.win.hover(self.mapToScene(p))
            return
        d, self._pan = p - self._pan, p
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            self.unsetCursor()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.win.timer.start()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.finish()


class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ROI Cropper")
        self.resize(1400, 850)
        self.setAcceptDrops(True)
        self.st = {}  # 경로 -> {'rois': [[pts, 번호]], 'f': 필터값}
        self.path = self.img = self.out = self.pix = self.ov = self.draft = self.hov = None
        self.cur, self.items, self.last = [], [], {}  # last: 카테고리 -> 마지막 입력 라벨
        self.scene = QGraphicsScene(self)
        self.view = View(self)
        self.timer = QTimer(self, singleShot=True, interval=30, timeout=self.update_overlay)
        self.build_ui()
        for keys, fn in [("Return", self.finish), ("Enter", self.finish), ("Esc", self.cancel), ("Backspace", self.undo),
                         ("Delete", self.delete_roi), ("Ctrl+S", self.save_all), ("Ctrl+O", self.open_files),
                         ("F", self.fit), ("1", self.actual),
                         ("[", lambda: self.step_cat(-1)), ("]", lambda: self.step_cat(1))]:
            QShortcut(QKeySequence(keys), self, activated=fn)
        for sb in (self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            sb.valueChanged.connect(lambda _: self.timer.start())  # 이동 시 보이는 영역 미리보기 갱신

    # ---------- UI ----------
    def build_ui(self):
        def btn(text, fn):
            b = QPushButton(text)
            b.clicked.connect(fn)
            return b

        left = QVBoxLayout()
        left.addWidget(btn("파일 열기 (Ctrl+O)", self.open_files))
        left.addWidget(btn("폴더 열기", self.open_folder))
        self.files = QListWidget()
        self.files.currentItemChanged.connect(lambda it, _: it and self.show_image(it.data(Qt.UserRole)))
        left.addWidget(self.files)
        hint = QLabel("※ 파일/폴더를 창에 드래그 앤 드롭해도 됩니다.")
        hint.setWordWrap(True)
        left.addWidget(hint)

        out = QGroupBox("저장")
        o = QVBoxLayout(out)
        o.addWidget(btn("저장 폴더 선택", self.pick_out))
        self.out_lab = QLabel("(미지정)")
        self.out_lab.setWordWrap(True)
        self.fmt = NoWheelCombo()
        self.fmt.addItems(["PNG", "TIFF"])
        self.alpha_cb = QCheckBox("제거 영역 투명 (해제=검정)")
        self.alpha_cb.setChecked(True)
        for w in (self.out_lab, self.fmt, self.alpha_cb):
            o.addWidget(w)

        cat = QGroupBox("카테고리 ( [ ] 키로 전환)")
        c = QVBoxLayout(cat)
        self.cat = NoWheelCombo()
        self.cat.addItem("(없음)")
        cb = QHBoxLayout()
        cb.addWidget(btn("추가", self.add_cat))
        cb.addWidget(btn("목록에서 제거", lambda: self.cat.currentIndex() > 0 and self.cat.removeItem(self.cat.currentIndex())))
        c.addWidget(self.cat)
        c.addLayout(cb)
        c.addWidget(btn("선택 ROI에 적용", self.apply_cat))

        self.roi_list = QListWidget()
        self.roi_list.currentRowChanged.connect(lambda _: self.on_select())
        self.roi_list.itemDoubleClicked.connect(lambda _: self.relabel())
        rbtn = QHBoxLayout()
        rbtn.addWidget(btn("삭제 (Del)", self.delete_roi))
        rbtn.addWidget(btn("번호 수정", self.relabel))

        self.dflt = list(DEFAULT)
        flt = self.fbox = QGroupBox()
        fl = QVBoxLayout(flt)
        self.sl, self.labs = [], []
        for i in range(len(SLIDERS)):
            lab, s = QLabel(), NoWheelSlider(Qt.Horizontal)
            s.setRange(0, LIMITS[i])
            s.valueChanged.connect(lambda v, i=i: self.on_slider(i, v))
            self.labs.append(lab)
            self.sl.append(s)
            fl.addWidget(lab)
            fl.addWidget(s)
        self.preview = QCheckBox("미리보기 (빨강 = 제거됨)")
        self.preview.setChecked(True)
        self.preview.toggled.connect(self.update_overlay)
        fl.addWidget(self.preview)
        fl.addWidget(btn("필터 초기화", lambda: (self.set_filter(DEFAULT), self.store_filter(), self.update_overlay())))

        right = QVBoxLayout()
        right.addWidget(out)
        right.addWidget(cat)
        right.addWidget(QLabel("ROI 목록 (현재 이미지)"))
        right.addWidget(self.roi_list)
        right.addLayout(rbtn)
        right.addWidget(flt)
        right.addWidget(btn("선택 ROI 저장", lambda: self.save([self.roi_list.currentRow()])))
        right.addWidget(btn("전체 ROI 저장 (Ctrl+S)", self.save_all))
        help_ = QLabel("좌클릭 점 추가 · 더블클릭/Enter/첫 점 클릭 = 닫기\nBackspace 점 취소 · Esc 취소\n"
                       "휠 확대/축소 · 우클릭 드래그 이동 · F 맞춤 · 1 100%")
        help_.setWordWrap(True)
        right.addWidget(help_)

        lw, inner, rw = QWidget(), QWidget(), QScrollArea()
        lw.setLayout(left)
        inner.setLayout(right)
        rw.setWidget(inner)
        rw.setWidgetResizable(True)
        rw.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lw.setFixedWidth(220)
        rw.setFixedWidth(340)
        root = QWidget()
        h = QHBoxLayout(root)
        h.addWidget(lw)
        h.addWidget(self.view, 1)
        h.addWidget(rw)
        self.setCentralWidget(root)
        self.zoom_lab = QLabel()
        self.statusBar().addPermanentWidget(self.zoom_lab)
        self.set_filter(DEFAULT)
        self.fbox.setTitle("필터 — 새 ROI 기본값")

    # ---------- 파일 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls()])

    def open_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "이미지 선택", "", "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.webp)")
        self.add_paths(fs)

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if d:
            self.add_paths([d])

    def add_paths(self, paths):
        fs = []
        for p in map(Path, paths):
            if p.is_dir():
                fs += sorted(q for q in p.iterdir() if q.suffix.lower() in EXTS)
            elif p.suffix.lower() in EXTS:
                fs.append(p)
        known = {self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())}
        new = [str(f) for f in fs if str(f) not in known]
        first = self.files.count()
        for f in new:
            it = QListWidgetItem(Path(f).name)
            it.setData(Qt.UserRole, f)
            self.files.addItem(it)
        if new and self.img is None:
            self.files.setCurrentRow(first)

    def show_image(self, path):
        self.scene.clear()
        self.path = self.img = self.pix = self.ov = self.draft = None
        self.items, self.cur = [], []
        gc.collect()
        try:
            im = Img(path)
        except Exception as e:
            QMessageBox.warning(self, "불러오기 실패", f"{path}\n\n{e}")
            self.fill_list()
            return
        self.img, self.path = im, path
        self.pix = self.scene.addPixmap(im.pix)
        self.ov = self.scene.addPixmap(QPixmap())
        self.ov.setZValue(1)
        self.scene.setSceneRect(self.pix.boundingRect())
        self.st.setdefault(path, {"rois": []})
        self.fill_list()
        self.fit()
        self.statusBar().showMessage(f"{Path(path).name}  {im.w}x{im.h}  {im.rgb.dtype}", 5000)

    # ---------- 뷰 ----------
    def fit(self):
        if self.pix:
            self.view.fitInView(self.pix, Qt.KeepAspectRatio)
            self.on_zoom()

    def actual(self):
        self.view.resetTransform()
        self.on_zoom()

    def on_zoom(self):
        self.zoom_lab.setText(f"{self.view.transform().m11() * 100:.0f}%")
        self.draw_draft()
        self.timer.start()

    def hover(self, p):
        if self.img:
            self.statusBar().showMessage(f"x={p.x():.0f}  y={p.y():.0f}")
        if self.cur:
            self.hov = p
            self.draw_draft()

    # ---------- 폴리곤 그리기 ----------
    def click(self, pos):
        if not self.img:
            return
        p = QPointF(min(max(pos.x(), 0), self.img.w), min(max(pos.y(), 0), self.img.h))
        if len(self.cur) >= 3 and (self.view.mapFromScene(self.cur[0]) - self.view.mapFromScene(p)).manhattanLength() < 12:
            return self.finish()
        self.cur.append(p)
        self.draw_draft()

    def undo(self):
        if self.cur:
            self.cur.pop()
            self.draw_draft()

    def cancel(self):
        self.cur = []
        self.draw_draft()

    def draw_draft(self):
        if self.draft:
            self.scene.removeItem(self.draft)
            self.draft = None
        if not self.cur:
            return
        r = 4 / self.view.transform().m11()
        path = QPainterPath(self.cur[0])
        for q in self.cur[1:] + ([self.hov] if self.hov else []):
            path.lineTo(q)
        for q in self.cur:
            path.addEllipse(q, r, r)
        pen = QPen(QColor("yellow"), 2)
        pen.setCosmetic(True)
        self.draft = self.scene.addPath(path, pen)
        self.draft.setZValue(3)

    def finish(self):
        if len(self.cur) < 3 or not self.img:
            return
        cat = self.cur_cat()
        last = self.last.get(cat, "0")
        n = self.ask_label("라벨 입력", str(int(last) + 1) if last.isdigit() else last)
        if n is None:  # 취소하면 그린 점은 유지 → 다시 Enter
            return
        f = [s.value() for s in self.sl]  # 새 ROI는 현재 슬라이더 값으로 시작
        self.rois().append([np.array([[p.x(), p.y()] for p in self.cur], np.float32), n, cat, f])
        self.last[cat], self.dflt, self.cur = n, f, []
        self.draw_draft()
        self.fill_list(select=len(self.rois()) - 1)

    # ---------- ROI 관리 ----------
    def rois(self):
        return self.st[self.path]["rois"]

    def ask_label(self, title, default):
        """번호/문자 라벨 입력. 파일명에 쓸 수 없는 문자는 거부. 취소 시 None."""
        while True:
            s, ok = QInputDialog.getText(self, title, "ROI 번호 또는 문자 (파일명에 사용됨):", text=default)
            if not ok:
                return None
            s = s.strip()
            if s and not re.search(r'[<>:"/\\|?*]', s):
                return s
            QMessageBox.warning(self, "입력 오류", '비어 있거나 사용할 수 없는 문자입니다: < > : " / \\ | ? *')

    def cur_cat(self):
        return "" if self.cat.currentIndex() == 0 else self.cat.currentText()

    def add_cat(self):
        s = self.ask_label("카테고리 추가", "")
        if s:
            if self.cat.findText(s) < 0:
                self.cat.addItem(s)
            self.cat.setCurrentText(s)

    def step_cat(self, d):
        self.cat.setCurrentIndex((self.cat.currentIndex() + d) % self.cat.count())

    def apply_cat(self):
        i = self.roi_list.currentRow()
        if i >= 0:
            self.rois()[i][2] = self.cur_cat()
            self.fill_list(select=i)

    @staticmethod
    def tag(n, cat):
        return f"{cat}-{n}" if cat else n

    def fill_list(self, select=-1):
        self.roi_list.blockSignals(True)
        self.roi_list.clear()
        if self.path:
            self.roi_list.addItems([f"{self.tag(n, c)}   ({len(p)}점)" for p, n, c, _ in self.rois()])
            self.roi_list.setCurrentRow(select)
            it = self.files.currentItem()
            if it:
                c = len(self.rois())
                it.setText(Path(self.path).name + (f"  [{c}]" if c else ""))
        self.roi_list.blockSignals(False)
        self.on_select()

    def on_select(self):
        """ROI 선택이 바뀌면 슬라이더를 그 ROI의 필터로 바꾸고 다시 그림 (선택 없음 = 새 ROI 기본값)."""
        i = self.roi_list.currentRow()
        roi = self.rois()[i] if self.path and i >= 0 else None
        self.set_filter(roi[3] if roi else self.dflt)
        self.fbox.setTitle(f"필터 — ROI {self.tag(roi[1], roi[2])}" if roi else "필터 — 새 ROI 기본값")
        self.draw_rois()
        self.update_overlay()

    def draw_rois(self):
        for it in self.items:
            self.scene.removeItem(it)
        self.items = []
        if not self.path:
            return
        sel = self.roi_list.currentRow()
        for i, (pts, n, c, _) in enumerate(self.rois()):
            pen = QPen(QColor("cyan" if i == sel else "lime"), 3 if i == sel else 2)
            pen.setCosmetic(True)
            poly = self.scene.addPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in pts]), pen, QBrush(QColor(0, 255, 0, 35)))
            t = self.scene.addSimpleText(self.tag(n, c))
            t.setBrush(QColor("yellow"))
            t.setFlag(t.GraphicsItemFlag.ItemIgnoresTransformations)
            t.setPos(float(pts[0][0]), float(pts[0][1]))
            poly.setZValue(2)
            t.setZValue(2)
            self.items += [poly, t]

    def delete_roi(self):
        i = self.roi_list.currentRow()
        if self.path and i >= 0:
            del self.rois()[i]
            self.fill_list()

    def relabel(self):
        i = self.roi_list.currentRow()
        if i < 0:
            return
        n = self.ask_label("라벨 수정", self.rois()[i][1])
        if n is not None:
            self.rois()[i][1] = n
            self.fill_list(select=i)

    # ---------- 필터 ----------
    def on_slider(self, i, v):
        if i % 2 == 0 and v > self.sl[i + 1].value():
            self.sl[i + 1].setValue(v)
        elif i % 2 == 1 and v < self.sl[i - 1].value():
            self.sl[i - 1].setValue(v)
        self.labs[i].setText(f"{SLIDERS[i]}: {v}")
        self.store_filter()
        self.timer.start()

    def store_filter(self):
        f, i = [s.value() for s in self.sl], self.roi_list.currentRow()
        if self.path and i >= 0:
            self.rois()[i][3] = f
        else:
            self.dflt = f

    def set_filter(self, f):
        for i, v in enumerate(f):
            self.sl[i].blockSignals(True)
            self.sl[i].setValue(v)
            self.sl[i].blockSignals(False)
            self.labs[i].setText(f"{SLIDERS[i]}: {v}")

    def update_overlay(self):
        im = self.img
        if not im or not self.ov:
            return
        if not self.preview.isChecked():
            self.ov.setPixmap(QPixmap())
            return
        # 보이는 영역이 작으면 원본 1픽셀 단위로, 크면(축소 보기) 축소본으로 계산
        vr = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        x0, y0 = max(int(vr.left()), 0), max(int(vr.top()), 0)
        x1, y1 = min(int(vr.right()) + 1, im.w), min(int(vr.bottom()) + 1, im.h)
        if x1 <= x0 or y1 <= y0:
            self.ov.setPixmap(QPixmap())
            return
        if (x1 - x0) * (y1 - y0) <= NATIVE_MAX:
            src, s, off = im.to8(im.rgb[y0:y1, x0:x1]), 1.0, (x0, y0)
        else:
            src, s, off = im.p8, im.scale, (0, 0)
        rs = self.rois()
        if rs:  # ROI별로 자기 필터를 자기 영역(bbox) 안에서만 평가
            removed = np.zeros(src.shape[:2], bool)
            for pts, _, _, f in rs:
                poly = np.round((pts - off) * s).astype(np.int32)
                bx0, by0 = poly.min(0).clip(0)
                bx1, by1 = np.minimum(poly.max(0) + 1, (src.shape[1], src.shape[0]))
                if bx1 <= bx0 or by1 <= by0:
                    continue
                m = np.zeros((by1 - by0, bx1 - bx0), np.uint8)
                cv2.fillPoly(m, [poly - (bx0, by0)], 1)
                removed[by0:by1, bx0:bx1] |= (keep_mask(src[by0:by1, bx0:bx1], f) == 0) & (m > 0)
        else:  # ROI가 없으면 새 ROI 기본값을 이미지 전체에 미리보기
            removed = keep_mask(src, self.dflt) == 0
        a = np.where(removed, np.uint32(0x780000FF), np.uint32(0))  # 리틀엔디언 RGBA = (255,0,0,120)
        self.ov.setPixmap(QPixmap.fromImage(QImage(a.data, a.shape[1], a.shape[0], a.shape[1] * 4, QImage.Format_RGBA8888)))
        self.ov.setScale(1 / s)
        self.ov.setPos(*off)

    # ---------- 저장 ----------
    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.out or "")
        if d:
            self.out = d
            self.out_lab.setText(d)

    def save_all(self):
        if self.path:
            self.save(range(len(self.rois())))

    def save(self, idx):
        if not self.img or not any(i >= 0 for i in idx):
            return
        if not self.out:
            self.pick_out()
            if not self.out:
                return
        ext = ".png" if self.fmt.currentIndex() == 0 and self.img.rgb.dtype in (np.uint8, np.uint16) else ".tif"
        stem, rows = Path(self.path).stem, []
        try:
            for i in idx:
                pts, n, c, f = self.rois()[i]
                dst = Path(self.out) / f"{'_'.join(filter(None, (stem, c, n)))}{ext}"
                if dst.exists() and QMessageBox.question(self, "덮어쓰기", f"{dst.name} 이(가) 이미 있습니다. 덮어쓸까요?") != QMessageBox.Yes:
                    continue
                try:
                    a, kept, (bx, by) = extract(self.img, pts, f, self.alpha_cb.isChecked())
                    if kept == 0:
                        QMessageBox.warning(self, "빈 결과", f"ROI {self.tag(n, c)}: 필터 후 남은 픽셀이 없어 저장하지 않았습니다.")
                        continue
                    write_img(dst, a)
                except Exception as e:
                    QMessageBox.critical(self, "저장 실패", f"{dst}\n\n{e}")
                    return
                rows.append(dict(zip(CSV_COLS, [
                    datetime.now().isoformat(timespec="seconds"), self.path, dst.name, c, n, kept,
                    round(float(cv2.contourArea(pts)), 1), bx, by, a.shape[1], a.shape[0], *f,
                    ";".join(f"{x:.1f} {y:.1f}" for x, y in pts)])))
        finally:  # 중간에 실패해도 이미 저장된 ROI는 기록
            if rows:
                try:
                    update_csv(Path(self.out) / f"{stem}_rois.csv", rows)
                except OSError as e:
                    QMessageBox.critical(self, "CSV 저장 실패", f"이미지는 저장됐지만 CSV를 쓰지 못했습니다 (엑셀에서 열려 있나요?)\n\n{e}")
        self.statusBar().showMessage(f"{len(rows)}개 저장 완료 → {self.out}", 5000)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Win()
    w.show()
    w.add_paths(sys.argv[1:])
    sys.exit(app.exec())
