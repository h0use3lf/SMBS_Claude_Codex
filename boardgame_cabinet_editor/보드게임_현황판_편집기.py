"""보드게임 현황판 편집기

캐비닛 4개 × 칸 5개의 보드게임 목록을 화면에서 자유롭게 입력/수정하고,
언제든 인쇄(복사)용 엑셀(캐비닛 1~4 시트)을 자동으로 만들어주는 프로그램.

인쇄용 시트 배치 규칙
  - 한 페이지는 "왼쪽 45줄 + 오른쪽 45줄" 두 칼럼으로 구성된다.
  - 칸(1~5)은 순서대로 왼쪽 칼럼부터 채워 내려가며, 칼럼이 다 차면 오른쪽 칼럼으로,
    오른쪽 칼럼도 다 차면 다음 페이지(새 칼럼 세트)로 넘어간다.
  - 한 칸의 게임 목록은 현재 칼럼에 다 들어가지 않으면 절대 중간에서 잘라 쓰지 않고
    통째로 다음 칼럼으로 넘긴다. (한 칸의 게임 수가 45개를 넘는 예외적인 경우에만
    부득이하게 여러 칼럼에 이어서 표시한다.)

데이터 저장 (엑셀 파일과 분리)
  - 실제 데이터는 이 프로그램(exe) 옆에 생기는 로컬 데이터베이스 파일
    ("보드게임_데이터.json")이 원본이며, 엑셀 파일과는 무관하게 독립적으로 저장된다.
  - 그 컴퓨터에 로컬 데이터베이스가 아직 없으면(=처음 실행), 프로그램에 내장된 기본
    데이터(DEFAULT_DATA)로 새로 만든다. 작업자가 바뀌어 다른 컴퓨터에서 실행해도 항상
    바로 쓸 수 있고, 그 이후 편집 내용은 그 컴퓨터의 로컬 데이터베이스에 쌓인다.
  - "엑셀에서 가져오기"로 기존 인쇄용 엑셀 파일의 데이터를 불러와 현재 작업 내용을
    통째로 바꿔칠 수 있고, "엑셀로 내보내기"로 현재 데이터를 인쇄용 엑셀로 만들 수 있다.
    인쇄용 시트는 이 프로그램이 그때그때 새로 그려주는 결과물이므로 직접 손으로 고치지
    않는다.

캐비닛 층수
  - 캐비닛 문을 열었을 때 그 칸이 몇 번째 층(선반)에 있는지를 나타내며, 칸 번호와
    그대로 같다 (칸1=1층 ... 칸5=5층). 그래서 별도 입력 없이 칸 번호를 그대로 인쇄용
    시트의 "캐비닛 층수" 칼럼에 표시한다.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.properties import PageSetupProperties

CABINET_COUNT = 4
SLOTS_PER_CABINET = 5
ROWS_PER_COLUMN = 45
BLOCK_ROWS = ROWS_PER_COLUMN + 2  # 머리글 1줄 + 데이터 45줄 + 구분줄 1줄 (인쇄용 시트 한 블록)
DB_SHEET_NAME = "DB_원본데이터"
LOCAL_DB_FILENAME = "보드게임_데이터.json"

SLOT_COLORS = ["FFEA9999", "FFF9CB9C", "FFFFE599", "FFB6D7A8", "FFA4C2F4"]

# 로컬 데이터베이스가 아직 없는 컴퓨터에서 처음 실행할 때 채워 넣는 기본 데이터.
# (data[(캐비닛, 칸)] = [(게임명, 수량), ...])
DEFAULT_DATA = {
    # 예시: (캐비닛 번호, 칸 번호): [(게임명, 수량), ...]
    # 개인 소장 목록이 저장소에 들어가지 않도록 공개용 복사본에서는 비워뒀습니다.
    # 그대로 실행하면 빈 상태로 시작하고, '엑셀에서 가져오기'나 화면에서 직접
    # 입력하면 이후로는 로컬 데이터베이스(보드게임_데이터.json)에 쌓입니다.
}


# ---------------------------------------------------------------------------
# 데이터 모델: data[(캐비닛, 칸)] = [(게임명, 수량), ...]  (입력한 순서 유지)
# ---------------------------------------------------------------------------

def empty_data():
    return {(c, s): [] for c in range(1, CABINET_COUNT + 1) for s in range(1, SLOTS_PER_CABINET + 1)}


def default_data():
    """이 컴퓨터에 로컬 데이터베이스가 아직 없을 때 쓰는 시작 데이터(내장 기본값)의 복사본."""
    return {key: list(games) for key, games in DEFAULT_DATA.items()}


# ---------------------------------------------------------------------------
# 로컬 데이터베이스: 실제 데이터 원본. 프로그램(exe)과 같은 폴더에 저장/자동 로드되며,
# 어떤 엑셀 파일을 열었는지와는 무관하다 (작업자/컴퓨터가 바뀌어도 항상 이 파일을 본다).
# ---------------------------------------------------------------------------

def local_db_path():
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent
    return base_dir / LOCAL_DB_FILENAME


def _data_to_jsonable(data):
    return {f"{c}-{s}": [[name, qty] for name, qty in games] for (c, s), games in data.items()}


def _data_from_jsonable(obj):
    data = empty_data()
    for key, games in obj.items():
        try:
            cab_str, slot_str = key.split("-")
            slot_key = (int(cab_str), int(slot_str))
        except ValueError:
            continue
        if slot_key not in data:
            continue
        data[slot_key] = [(str(name), int(qty)) for name, qty in games]
    return data


def load_local_db():
    path = local_db_path()
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _data_from_jsonable(obj.get("games", {}))


def save_local_db(data):
    path = local_db_path()
    obj = {"games": _data_to_jsonable(data)}
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load_data_from_db_sheet(wb):
    if DB_SHEET_NAME not in wb.sheetnames:
        return None
    ws = wb[DB_SHEET_NAME]
    data = empty_data()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        cab, slot, _order, name, qty = (list(row) + [None] * 5)[:5]
        if cab is None or slot is None or not name:
            continue
        key = (int(cab), int(slot))
        if key not in data:
            continue
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            qty = 1
        data[key].append((str(name).strip(), max(qty, 1)))
    return data


def save_data_to_db_sheet(wb, data):
    if DB_SHEET_NAME in wb.sheetnames:
        del wb[DB_SHEET_NAME]
    ws = wb.create_sheet(DB_SHEET_NAME)
    ws.append(["캐비닛", "칸", "순서", "게임명", "수량"])
    for (cab, slot), games in data.items():
        for i, (name, qty) in enumerate(games, start=1):
            ws.append([cab, slot, i, name, qty])
    ws.sheet_state = "hidden"


# ---------------------------------------------------------------------------
# 기존 인쇄용 시트에서 최초 1회 데이터 가져오기 (DB 시트가 아직 없을 때만 시도)
# ---------------------------------------------------------------------------

def try_import_from_print_sheets(wb):
    data = empty_data()
    imported_sheets = []
    for cab in range(1, CABINET_COUNT + 1):
        ws = None
        for candidate in (f"캐비닛 {cab}", f"캐비넷 {cab}"):
            if candidate in wb.sheetnames:
                ws = wb[candidate]
                break
        if ws is None:
            continue
        imported_sheets.append(ws.title)
        _import_one_cabinet_sheet(ws, cab, data)
    if not imported_sheets:
        return None, []
    return data, imported_sheets


def _is_block_data_row(row):
    """머리글/구분줄이 47줄마다 반복되므로, 실제 게임이 들어가는 행(블록당 45줄)만 True."""
    pos = (row - 1) % BLOCK_ROWS
    return 1 <= pos <= ROWS_PER_COLUMN


def _import_one_cabinet_sheet(ws, cabinet, data):
    for slot_col, name_col, qty_col in ((2, 3, 4), (5, 6, 7)):  # (B,C,D) / (E,F,G)
        markers = []
        for row in range(2, ws.max_row + 1):
            if not _is_block_data_row(row):
                continue
            v = ws.cell(row=row, column=slot_col).value
            if isinstance(v, int) and 1 <= v <= SLOTS_PER_CABINET:
                markers.append((row, v))
        for i, (start_row, slot_no) in enumerate(markers):
            end_row = markers[i + 1][0] - 1 if i + 1 < len(markers) else start_row + ROWS_PER_COLUMN - 1
            for r in range(start_row, min(end_row, ws.max_row) + 1):
                if not _is_block_data_row(r):
                    continue
                name = ws.cell(row=r, column=name_col).value
                if not name or not isinstance(name, str) or name.startswith("#"):
                    continue
                qty = ws.cell(row=r, column=qty_col).value
                try:
                    qty = int(qty)
                except (TypeError, ValueError):
                    qty = 1
                data[(cabinet, slot_no)].append((name.strip(), max(qty, 1)))


LEGACY_SHEET_RE = re.compile(r"^캐비[닛넷] ?\d+( ?\(\d+\))?$")
CANONICAL_NAMES = {f"캐비닛 {c}" for c in range(1, CABINET_COUNT + 1)}


def cleanup_legacy_sheets(wb):
    for name in list(wb.sheetnames):
        if name in CANONICAL_NAMES or name == DB_SHEET_NAME:
            continue
        if LEGACY_SHEET_RE.match(name):
            del wb[name]


# ---------------------------------------------------------------------------
# 칸 배치 알고리즘: 왼쪽 45줄 -> 오른쪽 45줄 -> 다음 페이지 순서로 채움
# ---------------------------------------------------------------------------

def pack_cabinet(games_by_slot):
    pages = [{"left": [], "right": []}]
    col = 0  # 0=왼쪽, 1=오른쪽
    remaining = ROWS_PER_COLUMN

    def new_column():
        nonlocal col, remaining, pages
        if col == 0:
            col = 1
        else:
            pages.append({"left": [], "right": []})
            col = 0
        remaining = ROWS_PER_COLUMN

    for slot_no in range(1, SLOTS_PER_CABINET + 1):
        games = games_by_slot.get(slot_no, [])
        needed = len(games) if games else 1

        if needed > remaining:
            new_column()

        target_key = "left" if col == 0 else "right"
        if needed <= remaining:
            pages[-1][target_key].append((slot_no, games))
            remaining -= needed
        else:
            # 한 칸의 게임이 45개보다 많아 한 칼럼에 다 못 담는 예외 상황:
            # 부득이하게 여러 칼럼에 이어서 채운다.
            rest = games
            while rest:
                take = min(len(rest), remaining)
                chunk, rest = rest[:take], rest[take:]
                target_key = "left" if col == 0 else "right"
                pages[-1][target_key].append((slot_no, chunk))
                remaining -= take
                if rest:
                    new_column()
    return pages


# ---------------------------------------------------------------------------
# 인쇄용 시트 그리기
# ---------------------------------------------------------------------------

FONT_NAME = "ONE 모바일POP"  # 시트 전체에 통일해서 쓰는 폰트 (없는 PC에서는 기본 폰트로 대체됨)


def build_cabinet_sheet(wb, cabinet, games_by_slot):
    """원본 "보드게임 현황표" 파일의 캐비닛 시트 양식을 그대로 재현한다.

    한 블록 = 47줄(머리글 1줄 + 데이터 45줄 + 구분줄 1줄), 열 너비와 머리글
    배치(칸 표시 없이 게임명/수량/캐비닛 제목/캐비닛 층수만 표시)도 원본과 동일하게 맞춘다.
    캐비닛 층수(H열)는 칸 번호와 같으므로, 페이지 분할과 무관하게 각 페이지 상단에
    칸 1~5의 번호를 색으로 구분한 작은 안내표로 표시한다.
    """
    sheet_name = f"캐비닛 {cabinet}"
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws = wb.create_sheet(sheet_name)
    ws.sheet_view.view = "pageBreakPreview"

    widths = {"A": 4, "B": 2.5, "C": 28.75, "D": 3.75, "E": 2.5, "F": 28.75, "G": 3.75, "H": 7.5}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    thin = Side(style="thin")
    medium = Side(style="medium")
    double = Side(style="double")

    pages = pack_cabinet(games_by_slot)

    for p_idx, page in enumerate(pages):
        base = p_idx * BLOCK_ROWS + 1
        header_row = base
        data_start = base + 1
        data_end = data_start + ROWS_PER_COLUMN - 1
        gap_row = data_end + 1

        # 머리글 줄: 원본처럼 "칸" 칼럼은 라벨 없이 비워두고, 제목은 F칸에 크게 표시한다.
        ws.row_dimensions[header_row].height = 34.5
        header_texts = {3: "게임명", 4: "수량", 6: f"캐비닛 {cabinet}", 8: "캐비닛   층수"}
        for col in range(2, 9):
            hc = ws.cell(row=header_row, column=col, value=header_texts.get(col))
            hc.font = Font(name=FONT_NAME, size=22 if col == 6 else 11)
            hc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=(col == 8))
            top = medium
            bottom = medium
            left = medium if col == 2 else None
            right = medium if col == 8 else None
            hc.border = Border(left=left, right=right, top=top, bottom=bottom)

        for side_key, col_offset in (("left", 0), ("right", 3)):
            row_cursor = data_start
            slot_col, name_col, qty_col = 2 + col_offset, 3 + col_offset, 4 + col_offset

            for slot_no, chunk in page[side_key]:
                span = max(len(chunk), 1)
                start_r, end_r = row_cursor, row_cursor + span - 1

                if span > 1:
                    ws.merge_cells(start_row=start_r, start_column=slot_col, end_row=end_r, end_column=slot_col)
                slot_cell = ws.cell(row=start_r, column=slot_col, value=slot_no)
                slot_cell.font = Font(name=FONT_NAME, bold=True)
                slot_cell.fill = PatternFill("solid", fgColor=SLOT_COLORS[(slot_no - 1) % len(SLOT_COLORS)])
                slot_cell.alignment = Alignment(horizontal="center", vertical="center")

                for rr in range(start_r, end_r + 1):
                    top = medium if rr == start_r else thin
                    bottom = medium if rr == end_r else thin
                    ws.cell(row=rr, column=slot_col).border = Border(left=medium, right=double, top=top, bottom=bottom)
                    ws.cell(row=rr, column=name_col).border = Border(left=double, right=medium, top=top, bottom=bottom)
                    ws.cell(row=rr, column=qty_col).border = Border(left=medium, right=medium, top=top, bottom=bottom)
                    ws.row_dimensions[rr].height = 15.95

                for i, (name, qty) in enumerate(chunk):
                    rr = start_r + i
                    nc = ws.cell(row=rr, column=name_col, value=name)
                    nc.font = Font(name=FONT_NAME)
                    nc.alignment = Alignment(horizontal="left", vertical="center", indent=1)
                    qc = ws.cell(row=rr, column=qty_col, value=qty)
                    qc.font = Font(name=FONT_NAME)
                    qc.alignment = Alignment(horizontal="center", vertical="center")

                row_cursor = end_r + 1

            # 칸이 배정되지 않은 남은 줄도 같은 테두리 규칙으로 채워 표 형태를 유지한다.
            while row_cursor <= data_end:
                top = medium if row_cursor == data_start else thin
                bottom = medium if row_cursor == data_end else thin
                ws.cell(row=row_cursor, column=slot_col).border = Border(left=medium, right=double, top=top, bottom=bottom)
                ws.cell(row=row_cursor, column=name_col).border = Border(left=double, right=medium, top=top, bottom=bottom)
                ws.cell(row=row_cursor, column=qty_col).border = Border(left=medium, right=medium, top=top, bottom=bottom)
                ws.row_dimensions[row_cursor].height = 15.95
                row_cursor += 1

            # H열(캐비닛 층수): 칸 번호와 같은 값이므로, 페이지 상단에 칸 1~5 번호를
            # 한 줄씩 색으로 구분해 보여주는 안내표로 그린다.
            if col_offset == 0:
                for i in range(SLOTS_PER_CABINET):
                    rr = data_start + i
                    slot_no = i + 1
                    fc = ws.cell(row=rr, column=8, value=slot_no)
                    fc.font = Font(name=FONT_NAME, bold=True)
                    fc.fill = PatternFill("solid", fgColor=SLOT_COLORS[(slot_no - 1) % len(SLOT_COLORS)])
                    fc.alignment = Alignment(horizontal="center", vertical="center")
                for rr in range(data_start, data_end + 1):
                    top = medium if rr == data_start else thin
                    bottom = medium if rr == data_end else thin
                    cell = ws.cell(row=rr, column=8)
                    cell.border = Border(left=medium, right=medium, top=top, bottom=bottom)

        ws.merge_cells(start_row=gap_row, start_column=2, end_row=gap_row, end_column=8)
        ws.row_dimensions[gap_row].height = 15.95
        if p_idx < len(pages) - 1:
            ws.row_breaks.append(Break(id=gap_row))

    # "Fit to Page" 배율(fitToWidth/fitToHeight)은 Excel이 인쇄영역 전체를 자기 방식대로
    # 다시 나눠버려서 수동 페이지 나누기(위에서 넣은 row_breaks)를 무시한다. 그래서 배율은
    # 고정 축소율(scale)만 쓰고, 페이지 경계는 오직 수동 나누기로만 결정되게 한다.
    # 그 결과 인쇄영역은 B1:H47(1페이지), B{48}:H{94}(2페이지), ... 식으로 47줄씩 정확히 나뉜다.
    last_row = len(pages) * BLOCK_ROWS
    ws.print_area = f"B1:H{last_row}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.scale = 90
    ws.print_options.horizontalCentered = True
    return ws


def regenerate_print_sheets(wb, data):
    for cab in range(1, CABINET_COUNT + 1):
        games_by_slot = {s: data.get((cab, s), []) for s in range(1, SLOTS_PER_CABINET + 1)}
        build_cabinet_sheet(wb, cab, games_by_slot)
    cleanup_legacy_sheets(wb)


# ---------------------------------------------------------------------------
# 텍스트 <-> 목록 변환 ("게임명,수량" 한 줄에 하나씩)
# ---------------------------------------------------------------------------

def parse_lines(text):
    games = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "\t" in line:
            name, _, qty = line.partition("\t")
        elif "," in line:
            name, _, qty = line.rpartition(",")
        else:
            name, qty = line, "1"
        name = name.strip()
        try:
            qty_val = int(qty.strip())
        except ValueError:
            qty_val = 1
        if name:
            games.append((name, max(qty_val, 1)))
    return games


def format_lines(games):
    return "\n".join(f"{name},{qty}" for name, qty in games)


# ---------------------------------------------------------------------------
# 저장 시 파일명에 오늘 날짜 반영 ("이름 YY_MM_DD.xlsx")
# ---------------------------------------------------------------------------

DATE_SUFFIX_RE = re.compile(r"\s*\d{2}_\d{2}_\d{2}$")


def with_today_date(path):
    p = Path(path)
    stem = DATE_SUFFIX_RE.sub("", p.stem)
    today = datetime.now().strftime("%y_%m_%d")
    return str(p.with_name(f"{stem} {today}{p.suffix}"))


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

# -- 색/폰트 팔레트 (트렌디하고 대비가 뚜렷한 라이트 테마) ----------------------

BG = "#F3F4F8"
SURFACE = "#FFFFFF"
BORDER = "#E3E5ED"
TEXT = "#1F2430"
MUTED = "#6B7280"
ACCENT = "#4F46E5"
ACCENT_HOVER = "#4338CA"
ACCENT_LIGHT = "#EEF0FD"
SUCCESS = "#16A34A"
WARN = "#D97706"

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"

STATUS_STYLES = {
    "ok": "StatusDotOK.TLabel",
    "warn": "StatusDotWarn.TLabel",
    "muted": "StatusDotMuted.TLabel",
}


def _hex_rgb(argb_hex):
    """SLOT_COLORS의 ARGB(예: 'FFEA9999')를 Tk가 쓰는 '#RRGGBB'로 바꾼다."""
    return "#" + argb_hex[-6:]


def _make_swatch(argb_hex, size=14):
    img = tk.PhotoImage(width=size, height=size)
    img.put(_hex_rgb(argb_hex), to=(0, 0, size, size))
    return img


class _Tooltip:
    """레이블이 잘렸을 때(예: 전체 파일 경로) 마우스를 올리면 전체 내용을 보여준다."""

    def __init__(self, widget, text_getter):
        self.widget = widget
        self.text_getter = text_getter
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        text = self.text_getter()
        if not text:
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip, text=text, background=TEXT, foreground="white",
            font=(FONT_FAMILY, 9), padx=8, pady=4, justify="left",
        ).pack()

    def _hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class BoardGameEditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("보드게임 현황판 편집기")
        self.geometry("1080x680")
        self.minsize(860, 560)

        self.export_path = None  # 마지막으로 내보낸 인쇄용 엑셀 경로 (없으면 프로그램 옆에 기본 이름으로 만듦)
        self.data = None
        self.current_key = None
        self.dirty = False
        self.leaf_keys = {}
        self._text_font_size = 11
        self._slot_swatches = [_make_swatch(c) for c in SLOT_COLORS]

        self._setup_style()
        self._build_widgets()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._load_or_init_data()

    # -- 스타일/화면 구성 ---------------------------------------------------
    def _setup_style(self):
        self.configure(background=BG)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("Status.TFrame", background=SURFACE)
        style.configure("TPanedwindow", background=BG)
        style.configure("TScrollbar", background=SURFACE, troughcolor=BG, arrowcolor=MUTED)
        style.configure("TSeparator", background=BORDER)

        style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT_FAMILY, 10))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=(FONT_FAMILY, 17, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=(FONT_FAMILY, 9))
        style.configure("SectionTitle.TLabel", background=SURFACE, foreground=MUTED, font=(FONT_FAMILY, 10, "bold"))
        style.configure("SlotHeader.TLabel", background=SURFACE, foreground=TEXT, font=(FONT_FAMILY, 14, "bold"))
        style.configure("Hint.TLabel", background=SURFACE, foreground=MUTED, font=(FONT_FAMILY, 9))
        style.configure("Status.TLabel", background=SURFACE, foreground=TEXT, font=(FONT_FAMILY, 9))
        for name in ("StatusDotOK", "StatusDotWarn", "StatusDotMuted"):
            color = {"StatusDotOK": SUCCESS, "StatusDotWarn": WARN, "StatusDotMuted": MUTED}[name]
            style.configure(f"{name}.TLabel", background=SURFACE, foreground=color, font=(FONT_FAMILY, 12))

        style.configure(
            "Accent.TButton", background=ACCENT, foreground="white",
            font=(FONT_FAMILY, 10, "bold"), padding=(16, 9), borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)])

        style.configure(
            "Secondary.TButton", background=SURFACE, foreground=TEXT,
            font=(FONT_FAMILY, 10), padding=(13, 8), borderwidth=1, relief="solid",
        )
        style.map("Secondary.TButton", background=[("active", ACCENT_LIGHT)])

        style.configure(
            "Nav.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
            font=(FONT_FAMILY, 10), rowheight=30, borderwidth=0,
        )
        style.map("Nav.Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])

    def _build_widgets(self):
        header = ttk.Frame(self, padding=(20, 16))
        header.pack(side="top", fill="x")
        title_box = ttk.Frame(header)
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="🎲 보드게임 현황판", style="Title.TLabel").pack(anchor="w")
        self.path_var = tk.StringVar(value=f"데이터베이스: {LOCAL_DB_FILENAME}")
        self.path_label = ttk.Label(title_box, textvariable=self.path_var, style="Subtitle.TLabel")
        self.path_label.pack(anchor="w", pady=(2, 0))
        _Tooltip(self.path_label, lambda: str(local_db_path()))

        btn_box = ttk.Frame(header)
        btn_box.pack(side="right")
        ttk.Button(
            btn_box, text="📂 엑셀에서 가져오기", style="Secondary.TButton", command=self._import_from_excel_dialog
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            btn_box, text="📤 엑셀로 내보내기", style="Secondary.TButton", command=self._export_as_dialog
        ).pack(side="left")

        ttk.Separator(self, orient="horizontal").pack(side="top", fill="x")

        status_bar = ttk.Frame(self, style="Status.TFrame", padding=(20, 10))
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")
        status_bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="")
        self.status_dot = ttk.Label(status_bar, text="●", style="StatusDotMuted.TLabel")
        self.status_dot.pack(side="left", padx=(0, 8))
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")

        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True, padx=16, pady=12)

        sidebar = ttk.Frame(paned, style="Card.TFrame", padding=12, width=260)
        paned.add(sidebar, weight=1)

        ttk.Label(sidebar, text="캐비닛 · 칸", style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 8))
        tree_frame = ttk.Frame(sidebar, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, show="tree", style="Nav.Treeview")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("cabinet", font=(FONT_FAMILY, 10, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        editor = ttk.Frame(paned, style="Card.TFrame", padding=18)
        paned.add(editor, weight=3)

        slot_header = ttk.Frame(editor, style="Card.TFrame")
        slot_header.pack(fill="x")
        self.swatch_label = tk.Label(slot_header, width=2, height=1, bg=SURFACE, highlightthickness=0)
        self.swatch_label.pack(side="left", padx=(0, 10))
        self.slot_label_var = tk.StringVar(value="왼쪽에서 칸을 선택하세요")
        ttk.Label(slot_header, textvariable=self.slot_label_var, style="SlotHeader.TLabel").pack(side="left")

        ttk.Label(
            editor,
            text="한 줄에 게임 하나씩 — '게임명,수량' 형식 (수량 생략 시 1개)  ·  Ctrl +/− 로 글자 크기 조절",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 10))

        text_frame = ttk.Frame(editor, style="Card.TFrame", width=600, height=400)
        text_frame.pack(fill="both", expand=True)
        # 이 프레임 크기를 안의 Text 위젯 요청 크기에 맡기지 않는다. 그렇지 않으면 글자
        # 크기를 키울 때(Ctrl +/-) Text의 기본 80x24글자 요청 크기가 커지면서 창 전체
        # 레이아웃이 흔들리고 "전체 저장" 버튼까지 같이 움직여 버린다.
        text_frame.pack_propagate(False)
        self.text = tk.Text(
            text_frame, wrap="none", undo=True, font=(MONO_FAMILY, self._text_font_size),
            background=SURFACE, foreground=TEXT, insertbackground=TEXT,
            relief="solid", borderwidth=1, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT, padx=10, pady=8,
        )
        self.text.pack(side="left", fill="both", expand=True)
        tsb = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        tsb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=tsb.set)

        btns = ttk.Frame(editor, style="Card.TFrame")
        btns.pack(fill="x", pady=(14, 0))
        ttk.Button(
            btns, text="이 칸 저장 (임시)", style="Secondary.TButton", command=self._commit_current_textbox
        ).pack(side="left")
        ttk.Button(
            btns, text="💾 전체 저장  (Ctrl+S)", style="Accent.TButton", command=self._full_save
        ).pack(side="right")

        self._set_status("준비됨", "muted")

    def _bind_shortcuts(self):
        self.bind_all("<Control-s>", lambda e: self._full_save())
        self.bind_all("<Control-o>", lambda e: self._import_from_excel_dialog())
        self.bind_all("<Control-plus>", lambda e: self._adjust_text_font(1))
        self.bind_all("<Control-equal>", lambda e: self._adjust_text_font(1))
        self.bind_all("<Control-minus>", lambda e: self._adjust_text_font(-1))

    def _adjust_text_font(self, delta):
        self._text_font_size = max(8, min(24, self._text_font_size + delta))
        self.text.configure(font=(MONO_FAMILY, self._text_font_size))

    def _set_status(self, text, kind="muted"):
        self.status_var.set(text)
        self.status_dot.configure(style=STATUS_STYLES[kind])

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.leaf_keys = {}
        for cab in range(1, CABINET_COUNT + 1):
            parent = self.tree.insert("", "end", text=f"🗄  캐비닛 {cab}", open=True, tags=("cabinet",))
            for slot in range(1, SLOTS_PER_CABINET + 1):
                count = len(self.data.get((cab, slot), []))
                swatch = self._slot_swatches[(slot - 1) % len(self._slot_swatches)]
                iid = self.tree.insert(parent, "end", text=f"칸 {slot}   {count}개", image=swatch)
                self.leaf_keys[iid] = (cab, slot)

    # -- 데이터베이스(자동)/엑셀 가져오기·내보내기(수동) ------------------------
    def _load_or_init_data(self):
        """이 컴퓨터의 로컬 데이터베이스를 불러온다. 없으면(=이 컴퓨터에서 처음 실행)
        내장 기본 데이터로 새로 만들어서 바로 저장해 둔다."""
        data = load_local_db()
        if data is None:
            data = default_data()
            try:
                save_local_db(data)
                status_msg = f"이 컴퓨터에 데이터베이스가 없어 기본 데이터로 새로 만들었습니다 → {local_db_path()}"
            except OSError as e:
                status_msg = f"기본 데이터로 시작합니다 (로컬 저장 실패: {e})"
            self._set_status(status_msg, "muted")
        else:
            self._set_status(f"데이터베이스를 불러왔습니다 → {local_db_path()}", "ok")

        self.data = data
        self.current_key = None
        self.dirty = False
        self._refresh_tree()

    def _import_from_excel_dialog(self):
        if not self._confirm_discard_if_dirty():
            return
        path = filedialog.askopenfilename(
            title="가져올 엑셀 파일 선택",
            filetypes=[("Excel 파일", "*.xlsx")],
        )
        if not path:
            return
        try:
            wb = load_workbook(path)
        except Exception as e:
            messagebox.showerror("가져오기 실패", str(e))
            return

        data = load_data_from_db_sheet(wb)
        imported_msg = None
        if data is None:
            data, imported_sheets = try_import_from_print_sheets(wb)
            if data is None:
                messagebox.showwarning("가져오기 실패", "이 파일에서 보드게임 데이터를 찾지 못했습니다.")
                return
            imported_msg = "기존 시트({})에서 데이터를 가져왔습니다.".format(", ".join(imported_sheets))

        self.data = data
        self.current_key = None
        self.dirty = True
        self._refresh_tree()
        self._set_status("엑셀에서 가져왔습니다 · 전체 저장을 눌러야 데이터베이스에 반영됩니다", "warn")
        if imported_msg:
            messagebox.showinfo("가져오기", imported_msg)

    def _export_as_dialog(self):
        default_name = Path(with_today_date(str(self._default_export_base()))).name
        path = filedialog.asksaveasfilename(
            title="인쇄용 엑셀로 내보내기",
            defaultextension=".xlsx",
            filetypes=[("Excel 파일", "*.xlsx")],
            initialfile=default_name,
        )
        if not path:
            return
        self.export_path = path
        self._commit_current_textbox()
        self._export_excel(path)

    def _default_export_base(self):
        return local_db_path().with_name("보드게임 현황표.xlsx")

    def _export_excel(self, save_path):
        try:
            wb = Workbook()
            wb.remove(wb.active)
            save_data_to_db_sheet(wb, self.data)
            regenerate_print_sheets(wb, self.data)
            wb.save(save_path)
        except PermissionError:
            messagebox.showerror(
                "내보내기 실패",
                "엑셀 파일이 다른 프로그램(엑셀 등)에서 열려 있어 저장할 수 없습니다. 파일을 닫고 다시 시도하세요.\n"
                "(데이터베이스는 정상적으로 저장되었습니다)",
            )
            return False
        except Exception as e:
            messagebox.showerror(
                "내보내기 실패",
                f"인쇄용 엑셀을 만드는 중 오류가 발생했습니다 (데이터베이스는 정상적으로 저장되었습니다).\n{e}",
            )
            return False
        self.export_path = save_path
        return True

    def _confirm_discard_if_dirty(self):
        if not self.dirty:
            return True
        return messagebox.askyesno("저장하지 않은 변경사항", "저장하지 않은 변경사항이 있습니다. 계속할까요?")

    def _on_close(self):
        if self._confirm_discard_if_dirty():
            self.destroy()

    # -- 편집 --------------------------------------------------------------
    def _on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel or sel[0] not in self.leaf_keys:
            return
        self._commit_current_textbox()
        self.current_key = self.leaf_keys[sel[0]]
        cab, slot = self.current_key
        self.slot_label_var.set(f"캐비닛 {cab}  ·  칸 {slot}")
        self.swatch_label.configure(bg=_hex_rgb(SLOT_COLORS[(slot - 1) % len(SLOT_COLORS)]))
        self.text.delete("1.0", "end")
        self.text.insert("1.0", format_lines(self.data.get(self.current_key, [])))
        self.text.focus_set()

    def _commit_current_textbox(self):
        if self.current_key is None:
            return
        new_games = parse_lines(self.text.get("1.0", "end"))
        if new_games != self.data.get(self.current_key, []):
            self.data[self.current_key] = new_games
            self.dirty = True
            cab, slot = self.current_key
            for iid, key in self.leaf_keys.items():
                if key == self.current_key:
                    self.tree.item(iid, text=f"칸 {slot}   {len(new_games)}개")
                    break
            self._set_status(f"캐비닛 {cab} 칸 {slot} 수정됨 (아직 파일에 저장 전)", "warn")

    def _full_save(self):
        self._commit_current_textbox()

        # 1) 실제 데이터 원본: 이 컴퓨터의 로컬 데이터베이스에 항상 저장한다.
        try:
            save_local_db(self.data)
        except OSError as e:
            messagebox.showerror("저장 실패", f"로컬 데이터베이스를 저장하지 못했습니다.\n{e}")
            return

        # 2) 인쇄용 엑셀도 같이 만들어 둔다. 내보낼 위치를 아직 고르지 않았다면
        #    데이터베이스와 같은 폴더에 오늘 날짜가 붙은 이름으로 만든다.
        export_base = self.export_path or str(self._default_export_base())
        save_path = with_today_date(export_base)
        if not self._export_excel(save_path):
            return

        self.dirty = False
        self._set_status(
            f"저장 완료 ({datetime.now():%H:%M:%S}) · DB: {LOCAL_DB_FILENAME}  ·  엑셀: {Path(save_path).name}",
            "ok",
        )


def main():
    app = BoardGameEditorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
