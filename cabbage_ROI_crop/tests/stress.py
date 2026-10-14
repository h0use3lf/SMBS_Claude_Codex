"""정확성 + 안정성 테스트 (offscreen). 사용: python tests/stress.py [반복횟수=200] [유휴초=20]"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
import psutil
import tifffile
from PySide6.QtWidgets import QApplication, QMessageBox

import app

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)  # 덮어쓰기 자동 승인
QMessageBox.warning = QMessageBox.critical = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[1:])))

N, IDLE = int(sys.argv[1]) if len(sys.argv) > 1 else 200, int(sys.argv[2]) if len(sys.argv) > 2 else 20
tmp = Path(tempfile.mkdtemp())
qa = QApplication([])
proc = psutil.Process()
rng = np.random.default_rng(0)

# 테스트 이미지: 16bit RGB tif(4000x3000), 8bit png(3000x3000), 16bit 그레이 tif
a16 = rng.integers(0, 65536, (3000, 4000, 3), dtype=np.uint16)
tifffile.imwrite(tmp / "a16.tif", a16)
cv2.imencode(".png", rng.integers(0, 256, (3000, 3000, 3), dtype=np.uint8))[1].tofile(str(tmp / "b8.png"))
tifffile.imwrite(tmp / "g16.tif", rng.integers(0, 65536, (2000, 2000), dtype=np.uint16))

w = app.Win()
w.show()
w.add_paths([str(tmp)])
out = tmp / "out"
out.mkdir()
w.out = str(out)
SQ = np.array([[100, 100], [900, 120], [800, 700], [150, 650]], np.float32)

# --- 정확성: 16bit 무손실 + 필터 + 알파 ---
w.files.setCurrentRow(0)
assert w.img.rgb.dtype == np.uint16 and np.array_equal(w.img.rgb, a16), "16bit 원본 손상"
w.rois().append([SQ.copy(), "7", "", list(app.DEFAULT)])
w.fill_list(select=0)
w.save([0])
r = cv2.imdecode(np.fromfile(str(out / "a16_7.png"), np.uint8), cv2.IMREAD_UNCHANGED)
assert r.dtype == np.uint16 and r.shape[2] == 4, "PNG 16bit RGBA 아님"
x0, y0, x1, y1 = 100, 100, 900, 700
inside = r[..., 3] > 0
assert np.array_equal(r[..., :3][inside][:, ::-1], a16[y0:y1, x0:x1][inside]), "크롭 픽셀값 손상"
assert not inside[-1, 0] and inside[300, 400], "폴리곤 마스크 오류"
w.fmt.setCurrentIndex(1)
w.sl[1].setValue(60)  # 선택된 ROI 0에만: Gray<=60 만 유지 → 대부분 제거
w.rois().append([SQ.copy() + 200, "8", "", list(app.DEFAULT)])
w.fill_list(select=1)
assert w.sl[1].value() == 255 and w.rois()[0][3][1] == 60, "ROI 간 필터가 섞임"
w.fill_list(select=0)
assert w.sl[1].value() == 60, "선택 시 ROI 필터가 슬라이더에 로드되지 않음"
w.save([0])
t = tifffile.imread(out / "a16_7.tif")
assert 0 < (t[..., 3] > 0).sum() < inside.sum() * 0.2, "필터 미적용"
w.save([1])
t8 = tifffile.imread(out / "a16_8.tif")
assert (t8[..., 3] > 0).sum() > 0.9 * inside.sum(), "ROI 1은 필터 없이 유지돼야 함"
del w.rois()[1]
w.fill_list(select=0)
w.rois()[0][2] = "줄1"
w.save([0])
assert (out / "a16_줄1_7.tif").exists(), "카테고리 파일명"
w.save([0])  # 같은 ROI 재저장 → CSV 행이 중복되면 안 됨
import csv
with open(out / "a16_rois.csv", encoding="utf-8-sig") as fh:
    rows = list(csv.DictReader(fh))
files = [r["file"] for r in rows]
assert len(files) == len(set(files)) and "a16_줄1_7.tif" in files and "a16_8.tif" in files, f"CSV 행 오류: {files}"
r = next(r for r in rows if r["file"] == "a16_줄1_7.tif")
assert (r["category"], r["label"], r["gray_max"], r["bbox_x"], r["bbox_w"]) == ("줄1", "7", "60", "100", "800"), r
assert int(r["kept_px"]) == (t[..., 3] > 0).sum(), "CSV kept_px 불일치"
assert not any(out.glob("b8_rois.csv")), "다른 이미지 CSV가 생기면 안 됨"
w.actual()
qa.processEvents()
w.update_overlay()
assert w.ov.scale() == 1.0 and w.ov.pixmap().width() < 4000, "확대 시 원본 1픽셀 미리보기 아님"
w.fit()
w.update_overlay()
assert w.ov.scale() > 1.0,"축소 보기에서는 축소본 사용"
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
for wd, get in ((w.sl[0], w.sl[0].value), (w.fmt, w.fmt.currentIndex), (w.cat, w.cat.currentIndex)):
    v = get()
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    qa.sendEvent(wd, ev)
    assert get() == v and not ev.isAccepted(), f"{type(wd).__name__} 휠 동작함"
print("정확성 OK")

# --- 안정성 ---
def rss():
    return proc.memory_info().rss / 2**20

proc.cpu_percent()
base, t0, samples = None, time.time(), []
for n in range(N):
    for row in range(w.files.count()):
        w.files.setCurrentRow(row)
        w.rois().clear()
        for k in range(5):
            w.cur = [app.QPointF(*p) for p in (SQ + k * 40)]
            w.hov = app.QPointF(10, 10)
            w.draw_draft()
            w.rois().append([(SQ + k * 40).copy(), f"r{k}", "줄1" if k % 2 else "", list(app.DEFAULT)])
        w.fill_list()
        w.draw_rois()
        for v in (50, 120, 200):
            w.sl[1].setValue(v)
            w.sl[5].setValue(v)
            w.update_overlay()
        for _ in range(3):
            w.view.scale(1.25, 1.25)
            w.on_zoom()
        w.fit()
        w.fmt.setCurrentIndex(n % 2)
        w.save_all()
        shutil.rmtree(out)
        out.mkdir()
        qa.processEvents()
    if n == min(4, N - 1):
        base = rss()  # 워밍업 후 기준
    if n % 10 == 0:
        samples.append(rss())
        print(f"cycle {n:4d}  RSS={samples[-1]:7.0f} MB  CPU={proc.cpu_percent():5.1f}%  {time.time() - t0:6.0f}s", flush=True)
growth = rss() - base
print(f"워밍업 후 메모리 증가: {growth:+.0f} MB (기준 {base:.0f} MB, 최대 {max(samples):.0f} MB)")

# 유휴: 창만 켜둔 상태의 CPU
proc.cpu_percent()
end = time.time() + IDLE
while time.time() < end:
    qa.processEvents()
    time.sleep(0.05)
idle = proc.cpu_percent() / 1
print(f"유휴 {IDLE}s 평균 CPU: {idle:.1f}% (이벤트 폴링 루프 포함이라 실제 앱보다 높게 측정됨)")
assert growth < 300, "메모리 누수 의심"
shutil.rmtree(tmp, ignore_errors=True)
print("안정성 OK")
