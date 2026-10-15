"""PySide6 데스크톱 UI."""
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
                               QDateEdit, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import charts, core, report

DATA_DIR = Path.home() / "Documents" / "현금흐름관리"
DATA_FILE = DATA_DIR / "data.json"

QSS = """
* { font-family: 'Pretendard', 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans CJK KR'; font-size: 13px; color: #0F172A; }
QMainWindow, #content { background: #F4F6FA; }
#sidebar { background: #0F172A; }
#brand { color: #F8FAFC; font-size: 15px; font-weight: 700; padding: 22px 20px 4px 20px; }
#brandSub { color: #64748B; font-size: 11px; padding: 0 20px 18px 20px; }
#nav { background: transparent; color: #94A3B8; text-align: left; padding: 11px 20px; border: none;
       border-left: 3px solid transparent; font-size: 13px; }
#nav:hover { color: #E2E8F0; background: #1E293B; }
#nav:checked { color: #FFFFFF; background: #1E293B; border-left: 3px solid #3B82F6; font-weight: 600; }
#pageTitle { font-size: 22px; font-weight: 700; }
#pageSub { color: #64748B; font-size: 12px; }
#card { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; }
#cardTitle { font-size: 14px; font-weight: 700; }
#hint { color: #64748B; font-size: 11px; }
#kpiLabel { color: #64748B; font-size: 11px; }
#kpiValue { font-size: 19px; font-weight: 700; }
#chip { background: #EFF6FF; color: #1D4ED8; border-radius: 10px; padding: 4px 10px; font-size: 12px; }
#warn { background: #FEF2F2; color: #B91C1C; border-radius: 8px; padding: 8px 12px; }
#ok { background: #ECFDF5; color: #047857; border-radius: 8px; padding: 8px 12px; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit {
    background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 7px; padding: 6px 8px; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border: 1px solid #3B82F6; }
QComboBox::drop-down { border: none; width: 22px; }
QPushButton { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 7px; padding: 7px 14px; }
QPushButton:hover { background: #F1F5F9; }
QPushButton#primary { background: #2563EB; color: white; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #1D4ED8; }
QPushButton#ghost { border: none; color: #2563EB; background: transparent; padding: 4px 6px; }
QPushButton#danger { color: #B91C1C; }
QPushButton#seg { border-radius: 0; padding: 7px 16px; }
QPushButton#seg:checked { background: #0F172A; color: white; border-color: #0F172A; }
QTableWidget { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; gridline-color: #F1F5F9;
               selection-background-color: #DBEAFE; selection-color: #0F172A; }
QHeaderView::section { background: #F8FAFC; border: none; border-bottom: 1px solid #E5E7EB;
                       padding: 7px 6px; font-weight: 600; color: #475569; font-size: 12px; }
QTableWidget QComboBox, QTableWidget QLineEdit { border: none; border-radius: 0; padding: 2px 4px; }
QScrollArea { border: none; background: transparent; }
QCheckBox { spacing: 8px; }
"""


def card(title=None, hint=None):
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(18, 16, 18, 16)
    v.setSpacing(10)
    if title:
        h = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("cardTitle")
        h.addWidget(t)
        h.addStretch()
        v.addLayout(h)
        f.head = h
    if hint:
        l = QLabel(hint)
        l.setObjectName("hint")
        l.setWordWrap(True)
        v.addWidget(l)
    return f, v


def button(text, kind=None, slot=None):
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


class DictTable(QTableWidget):
    """열 정의 [(key, 머리글, 종류[, 선택지])]: 종류 text|int|date|combo|ro"""
    edited = Signal()

    def __init__(self, cols, rows=None, height=200, stretch=None):
        super().__init__(0, len(cols))
        self.cols = cols
        self.setHorizontalHeaderLabels([c[1] for c in cols])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setMinimumHeight(height)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        for i in range(len(cols)):
            hh.setSectionResizeMode(i, QHeaderView.Stretch if (stretch is None or i in stretch)
                                    else QHeaderView.ResizeToContents)
        self.itemChanged.connect(lambda *_: self._loading or self.edited.emit())
        self._loading = False
        self.set_rows(rows or [])

    def _combo(self, opts, val):
        c = QComboBox()
        c.addItems(opts)
        if val in opts:
            c.setCurrentText(val)
        c.currentTextChanged.connect(lambda *_: self._loading or self.edited.emit())
        return c

    def add_row(self, r=None):
        r = r or {}
        self._loading = True
        i = self.rowCount()
        self.insertRow(i)
        for j, col in enumerate(self.cols):
            key, kind = col[0], col[2]
            v = r.get(key, "")
            if kind == "combo":
                self.setCellWidget(i, j, self._combo(col[3], v))
            else:
                if kind == "int" and v not in ("", None):
                    v = core.won(core.parse_amount(v))
                it = QTableWidgetItem("" if v is None else str(v))
                if kind == "int":
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if kind == "ro":
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setForeground(Qt.darkGray)
                self.setItem(i, j, it)
        self._loading = False

    def set_rows(self, rows):
        self._loading = True
        self.setRowCount(0)
        self._loading = False
        for r in rows:
            self.add_row(r)

    def rows(self):
        out = []
        for i in range(self.rowCount()):
            r = {}
            for j, col in enumerate(self.cols):
                key, kind = col[0], col[2]
                if kind == "combo":
                    r[key] = self.cellWidget(i, j).currentText()
                else:
                    it = self.item(i, j)
                    t = it.text().strip() if it else ""
                    if kind == "int":
                        r[key] = core.parse_amount(t) if t else ""
                    elif kind == "date" and t:
                        try:
                            r[key] = core.d(t.replace(".", "-").replace("/", "-")).isoformat()
                        except ValueError:
                            r[key] = t
                    else:
                        r[key] = t
            if any(str(v).strip() for k, v in r.items() if k not in ("type", "category")):
                out.append(r)
        return out

    def remove_selected(self):
        for i in sorted({ix.row() for ix in self.selectedIndexes()}, reverse=True):
            self.removeRow(i)
        self.edited.emit()


def table_block(title, hint, cols, rows, on_change, height=170, stretch=None):
    f, v = card(title, hint)
    t = DictTable(cols, rows, height, stretch)
    t.edited.connect(on_change)
    v.addWidget(t)
    f.head.addWidget(button("+ 행 추가", "ghost", lambda: (t.add_row(), on_change())))
    f.head.addWidget(button("선택 삭제", "ghost", t.remove_selected))
    return f, t


class Page(QScrollArea):
    def __init__(self, title, sub):
        super().__init__()
        self.setWidgetResizable(True)
        w = QWidget()
        w.setObjectName("content")
        self.setWidget(w)
        self.body = QVBoxLayout(w)
        self.body.setContentsMargins(32, 28, 32, 32)
        self.body.setSpacing(16)
        t = QLabel(title)
        t.setObjectName("pageTitle")
        s = QLabel(sub)
        s.setObjectName("pageSub")
        s.setWordWrap(True)
        self.body.addWidget(t)
        self.body.addWidget(s)

    def add(self, w):
        self.body.addWidget(w)

    def finish(self):
        self.body.addStretch()


def kpi(label, value=""):
    f, v = card()
    v.setContentsMargins(16, 12, 16, 12)
    v.setSpacing(2)
    l = QLabel(label)
    l.setObjectName("kpiLabel")
    n = QLabel(value)
    n.setObjectName("kpiValue")
    v.addWidget(l)
    v.addWidget(n)
    f.value = n
    return f


# ───────────────────────────── 페이지 ─────────────────────────────
class SetupPage(Page):
    def __init__(self, app):
        super().__init__("기본 정보", "생활 여건과 관리 범위, 기록 기간, 시작 시점의 재무상태를 입력합니다.")
        self.app = app
        D = app.data
        f, v = card("인적 사항 · 관리 범위")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.fields = {}
        spec = [("course", "교과목"), ("dept", "소속"), ("student_id", "학번"), ("name", "성명"),
                ("submit_date", "제출일"), ("title", "과제명"),
                ("life_type", "생활 형태", "예: 가족과 동거 / 자취 / 기숙사"),
                ("income_sources", "주요 소득", "예: 용돈, 아르바이트비, 생활비성 장학금"),
                ("managed", "관리 대상", "예: 체크카드, 입출금 계좌, 현금"),
                ("cost_split", "비용 구분", "예: 통신비·주거비는 부모님 납부로 본인 지출에서 제외")]
        for i, s in enumerate(spec):
            e = QLineEdit(D["profile"].get(s[0], ""))
            if len(s) > 2:
                e.setPlaceholderText(s[2])
            e.textChanged.connect(self.sync)
            self.fields[s[0]] = e
            r, c = (i // 2, (i % 2) * 2) if i < 6 else (3 + (i - 6), 0)
            grid.addWidget(QLabel(s[1]), r, c)
            grid.addWidget(e, r, c + 1, 1, 1 if i < 6 else 3)
        v.addLayout(grid)
        self.add(f)

        f, v = card("기록 기간", "기록 시작일부터 한 달을 예산 기간으로 하고, 상반기 일수만큼 끊어 2주 단위로 관리합니다.")
        h = QHBoxLayout()
        self.start = QDateEdit(QDate.fromString(D["period"]["start"], "yyyy-MM-dd"))
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("yyyy-MM-dd")
        self.split = QSpinBox()
        self.split.setRange(7, 21)
        self.split.setValue(int(D["period"]["split_days"]))
        self.split.setSuffix(" 일")
        self.hol = QLineEdit(", ".join(D["holidays"]))
        self.hol.setPlaceholderText("공휴일 YYYY-MM-DD, 쉼표 구분")
        for w in (self.start, self.split):
            (w.dateChanged if isinstance(w, QDateEdit) else w.valueChanged).connect(self.sync)
        self.hol.textChanged.connect(self.sync)
        for lab, w in (("시작일", self.start), ("상반기 일수", self.split), ("공휴일", self.hol)):
            h.addWidget(QLabel(lab))
            h.addWidget(w, 2 if w is self.hol else 0)
        v.addLayout(h)
        self.plabel = QLabel()
        self.plabel.setObjectName("chip")
        v.addWidget(self.plabel, 0, Qt.AlignLeft)
        self.add(f)

        f, self.assets = table_block(
            "재무상태 (기초 · 기말)", "유동자산(현금·입출금 계좌·체크카드 연결 계좌), 저축자산(적금·청약·투자), "
            "부채(신용카드 미결제액 등). 기말 금액은 기록 종료 후 실제 잔액을 확인해 입력합니다.",
            [("name", "계정", "text"), ("type", "구분", "combo", core.ASSET_TYPES),
             ("start", "기초 금액", "int"), ("end", "기말 금액(실제)", "int")], D["assets"], self.sync)
        self.add(f)
        f, self.family = table_block(
            "타인 부담 비용 (본인 지출에서 제외)", "부모님 등이 대신 납부하는 주거비·통신비 등은 여기에 별도로 기록합니다.",
            [("name", "항목", "text"), ("amount", "월 금액", "int"), ("payer", "부담자", "text"),
             ("note", "비고", "text")], D["family_paid"], self.sync, 130)
        self.add(f)
        self.finish()
        self.refresh_period()

    def sync(self, *_):
        D = self.app.data
        for k, e in self.fields.items():
            D["profile"][k] = e.text()
        D["period"]["start"] = self.start.date().toString("yyyy-MM-dd")
        D["period"]["split_days"] = self.split.value()
        hs = []
        for x in self.hol.text().replace(" ", "").split(","):
            try:
                hs.append(core.d(x).isoformat())
            except ValueError:
                pass
        D["holidays"] = hs
        D["assets"] = self.assets.rows()
        D["family_paid"] = self.family.rows()
        self.refresh_period()
        self.app.changed()

    def refresh_period(self):
        D = self.app.data
        self.plabel.setText(f"{core.period_title(D, 'p1')}  ·  {core.period_title(D, 'p2')}  ·  "
                            f"시작 가용 잔액 {core.won(core.start_liquid(D))}원")


class BudgetPage(Page):
    def __init__(self, app):
        super().__init__("예산 수립", "지난 기간 기록을 입력하면 기초 잔액·배분 비율·수입/저축/고정지출 계획이 역산됩니다. "
                                  "역산값은 직접 수정할 수 있고, 가용 예산 3개 안 중 하나를 선택하면 "
                                  "한 달 예산과 2주 기간 예산이 자동 배분됩니다.")
        self.app = app
        D = app.data
        H = D["history"]
        f, v = card("지난 기간 기록 → 자동 산출",
                    "시작점(날짜와 그날의 가용 현금)을 지정하고, 그날부터 기록 시작일 전날까지의 수입·지출·저축을 "
                    "빠짐없이 입력합니다(최소 2주). 분류를 '자동'으로 두면 항목명으로 분류하며, 구독료·회비는 '고정지출'로 지정합니다.")
        h = QHBoxLayout()
        ms = core.periods(D)["month"][0]
        self.h_start = QDateEdit(QDate.fromString(H["start"], "yyyy-MM-dd") if H.get("start")
                                 else QDate(ms.year, ms.month, ms.day).addDays(-14))
        self.h_start.setCalendarPopup(True)
        self.h_start.setDisplayFormat("yyyy-MM-dd")
        self.h_bal = QLineEdit("" if H.get("balance") in ("", None) else core.won(core.parse_amount(H["balance"])))
        self.h_bal.setPlaceholderText("시작일 가용 현금(계좌+현금)")
        self.h_bal.setFixedWidth(200)
        for lab, w in (("시작일", self.h_start), ("시작 잔액", self.h_bal)):
            h.addWidget(QLabel(lab))
            h.addWidget(w)
        h.addStretch()
        h.addWidget(button("지난 기록으로 산출", "primary", self.derive))
        v.addLayout(h)
        self.hist = DictTable([("date", "날짜(YYYY-MM-DD)", "date"), ("item", "항목", "text"),
                               ("amount", "금액", "int"), ("category", "분류", "combo", core.HIST_CATS)],
                              H.get("rows", []), 220)
        v.addWidget(self.hist)
        f.head.addWidget(button("+ 행 추가", "ghost", lambda: (self.hist.add_row(), self.sync_hist())))
        f.head.addWidget(button("선택 삭제", "ghost", self.hist.remove_selected))
        self.hres = QLabel()
        self.hres.setObjectName("hint")
        self.hres.setWordWrap(True)
        v.addWidget(self.hres)
        self.h_start.dateChanged.connect(self.sync_hist)
        self.h_bal.textChanged.connect(self.sync_hist)
        self.hist.edited.connect(self.sync_hist)
        self.add(f)
        cols =[("name", "항목", "text"), ("amount", "금액", "int"), ("date", "예정일(YYYY-MM-DD)", "date"),
                ("basis", "설정 근거", "text")]
        row = QHBoxLayout()
        f, self.inc = table_block("예상 수입", None, cols, D["incomes"], self.sync, 150)
        row.addWidget(f)
        f, self.sav = table_block("저축 계획 (소비 전 먼저)", None, cols, D["savings"], self.sync, 150)
        row.addWidget(f)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.add(w)
        row = QHBoxLayout()
        f, self.fix = table_block("고정지출 (구독료·회비 등)", None, cols, D["fixed"], self.sync, 150)
        row.addWidget(f)
        f, self.ev = table_block("예정 일정 (모임·교재 구매 등)", "해당 기간 예산에 먼저 반영됩니다.",
                                 [("date", "날짜", "date"), ("category", "카테고리", "combo", core.VAR_CATS),
                                  ("amount", "금액", "int"), ("note", "내용", "text")], D["events"], self.sync, 150)
        row.addWidget(f)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.add(w)

        f, v = card("변동지출 배분 비율", "선택한 안의 변동지출 금액을 아래 비율(%)로 카테고리에 나눕니다.")
        h = QHBoxLayout()
        self.w = {}
        for c in core.VAR_CATS:
            box = QVBoxLayout()
            l = QLabel(c)
            l.setObjectName("hint")
            s = QSpinBox()
            s.setRange(0, 100)
            s.setSuffix(" %")
            s.setValue(int(D["weights"].get(c, 0)))
            s.valueChanged.connect(self.sync)
            self.w[c] = s
            box.addWidget(l)
            box.addWidget(s)
            h.addLayout(box)
        self.wsum = QLabel()
        h.addWidget(self.wsum)
        v.addLayout(h)
        self.add(f)

        f, v = card("가용 예산 3개 안")
        f.head.addWidget(button("산출", "primary", self.compute))
        self.summary = QLabel()
        self.summary.setObjectName("hint")
        v.addWidget(self.summary)
        self.opt_row = QHBoxLayout()
        self.opt_row.setSpacing(12)
        v.addLayout(self.opt_row)
        self.choice_grp = QButtonGroup(self)
        self.add(f)

        f, v = card("한 달 · 2주 기간 예산", "변동지출의 '한 달' 금액과 설정 근거는 직접 수정할 수 있습니다. "
                                         "상반기·후반기는 평일·휴일 일수와 예정 일정으로 자동 계산됩니다.")
        self.btable = QTableWidget(0, 7)
        self.btable.setHorizontalHeaderLabels(["구분", "항목", "한 달", "상반기", "후반기", "설정 근거", "2주 설정 근거"])
        self.btable.verticalHeader().setVisible(False)
        self.btable.setMinimumHeight(560)
        hh = self.btable.horizontalHeader()
        for i in range(7):
            hh.setSectionResizeMode(i, QHeaderView.Stretch if i in (5, 6) else QHeaderView.ResizeToContents)
        self.btable.itemChanged.connect(self.budget_edit)
        v.addWidget(self.btable)
        self.bcheck = QLabel()
        v.addWidget(self.bcheck)
        self.add(f)
        self.finish()
        self.compute(silent=True)
        self.fill_budget()

    def sync(self, *_):
        D = self.app.data
        D["incomes"], D["savings"], D["fixed"] = self.inc.rows(), self.sav.rows(), self.fix.rows()
        D["events"] = self.ev.rows()
        D["weights"] = {c: s.value() for c, s in self.w.items()}
        tot = sum(D["weights"].values())
        self.wsum.setText(f"합계 {tot}%")
        self.wsum.setObjectName("ok" if tot == 100 else "warn")
        self.wsum.setStyleSheet("")
        self.app.changed()

    def sync_hist(self, *_):
        H = self.app.data["history"]
        H["start"] = self.h_start.date().toString("yyyy-MM-dd")
        t = self.h_bal.text().strip()
        H["balance"] = core.parse_amount(t) if t else ""
        H["rows"] = self.hist.rows()
        self.app.changed()

    def derive(self):
        self.sync_hist()
        D = self.app.data
        if D["history"]["balance"] == "":
            QMessageBox.information(self, "입력 확인", "시작일의 가용 현금(시작 잔액)을 입력하세요.")
            return
        r = core.derive_history(D)
        if not r["count"]:
            QMessageBox.information(self, "입력 확인", "시작일부터 기록 시작일 전날 사이의 기록이 없습니다.")
            return
        core.apply_history(D, r)
        self.inc.set_rows(D["incomes"])
        self.sav.set_rows(D["savings"])
        self.fix.set_rows(D["fixed"])
        for c, s in self.w.items():
            s.blockSignals(True)
            s.setValue(int(D["weights"].get(c, 0)))
            s.blockSignals(False)
        self.sync()
        setup = self.app.pages[0]
        setup.assets.set_rows(D["assets"])
        setup.refresh_period()
        if D["budget"].get("choice") and sum(D["weights"].values()) == 100:
            core.apply_choice(D, D["budget"]["choice"])
        self.compute(silent=True)
        self.fill_budget()
        a, b = r["range"]
        msg = [f"{a.month}/{a.day}~{b.month}/{b.day} ({r['days']}일) 기록 {r['count']}건: "
               f"시작 {core.won(core.parse_amount(D['history']['balance']))} + 수입 {core.won(r['income'])} − "
               f"지출 {core.won(r['expense'])} − 저축 {core.won(r['saving'])} = 기초 잔액 {core.won(r['balance'])}원",
               "배분 비율 " + (" · ".join(f"{c} {p}%" for c, p in r["weights"].items() if p)
                           if r["weights"] else "— 변동지출 기록이 없어 기존 비율 유지")]
        if r["days"] < 14:
            msg.append(f"기록 기간이 {r['days']}일로 2주 미만입니다.")
        if r["outside"] or r["bad"]:
            msg.append(f"기간 밖 {r['outside']}건 · 날짜 형식 오류 {r['bad']}건은 제외했습니다.")
        self.hres.setText("\n".join(msg))

    def compute(self, silent=False):
        self.sync()
        D = self.app.data
        bo = core.budget_options(D)
        while self.opt_row.count():
            it = self.opt_row.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.summary.setText(
            f"시작 가용 잔액 {core.won(bo['start'])}원 · 예상 수입 {core.won(bo['income'])}원 · "
            f"저축 {core.won(bo['savings'])}원 · 고정지출 {core.won(bo['fixed'])}원 → "
            f"수입 기준 여유 {core.won(bo['base'])}원")
        for k, o in bo["options"].items():
            f, v = card(f"{o['name']} ({k})")
            f.setMinimumWidth(240)
            d = QLabel(o["desc"])
            d.setObjectName("hint")
            d.setWordWrap(True)
            v.addWidget(d)
            big = QLabel(f"{core.won(o['available'])}원")
            big.setObjectName("kpiValue")
            v.addWidget(big)
            for lab, val in (("변동지출", o["variable"]), ("예비비", o["reserve"]),
                             ("이월 잔액 활용", o["carry_used"]), ("월말 예상 이월", o["carry_end"]),
                             ("일 평균 변동지출", int(o["daily"]))):
                h = QHBoxLayout()
                a = QLabel(lab)
                a.setObjectName("hint")
                b = QLabel(f"{core.won(val)}원")
                h.addWidget(a)
                h.addStretch()
                h.addWidget(b)
                v.addLayout(h)
            sel = button("✓ 선택됨" if D["budget"].get("choice") == k else "이 안 선택",
                         "primary" if D["budget"].get("choice") == k else None,
                         lambda _=False, k=k: self.choose(k))
            v.addWidget(sel)
            self.opt_row.addWidget(f)
        if bo["base"] <= 0 and not silent:
            QMessageBox.warning(self, "예산 확인", "예상 수입이 저축과 고정지출을 감당하지 못합니다. "
                                               "저축 계획 또는 고정지출을 조정하세요.")

    def choose(self, k):
        D = self.app.data
        if sum(D["weights"].values()) != 100:
            QMessageBox.warning(self, "배분 비율", "변동지출 배분 비율의 합계를 100%로 맞춰 주세요.")
            return
        core.apply_choice(D, k)
        self.compute(silent=True)
        self.fill_budget()
        self.app.changed()

    def fill_budget(self):
        D = self.app.data
        self._filling = True
        rows = core.budget_rows(D) if D["budget"].get("choice") else []
        self.btable.setRowCount(0)
        for r in rows:
            i = self.btable.rowCount()
            self.btable.insertRow(i)
            for j, v in enumerate(r):
                it = QTableWidgetItem(core.won(v) if j in (2, 3, 4) else str(v))
                if j in (2, 3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                editable = r[0] in ("변동지출", "예비비") and j in (2, 5)
                if not editable:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    if j in (0, 1, 3, 4, 6):
                        it.setForeground(Qt.darkGray if j in (0, 6) else Qt.black)
                self.btable.setItem(i, j, it)
        self._filling = False
        if rows:
            s = core.budget_summary(D)
            left = s["start"] + s["income"] - s["savings"] - s["fixed"] - s["variable"] - s["reserve"]
            self.bcheck.setText(f"검증: 소득 {core.won(s['start'] + s['income'])} − 저축 {core.won(s['savings'])} − "
                                f"고정 {core.won(s['fixed'])} − 변동 {core.won(s['variable'])} − 예비비 "
                                f"{core.won(s['reserve'])} = 월말 이월 예정 {core.won(left)}원")
            self.bcheck.setObjectName("ok" if left >= 0 else "warn")
            self.bcheck.setStyleSheet("")

    def budget_edit(self, it):
        if getattr(self, "_filling", False):
            return
        D = self.app.data
        r = it.row()
        grp, name = self.btable.item(r, 0).text(), self.btable.item(r, 1).text()
        if it.column() == 2:
            amt = core.parse_amount(it.text())
            if grp == "예비비":
                D["budget"]["reserve"] = amt
            else:
                D["budget"]["variable"][name] = amt
        elif it.column() == 5:
            D["budget"].setdefault("basis", {})[name] = it.text()
        QTimer.singleShot(0, self.fill_budget)
        self.app.changed()


class RecordPage(Page):
    def __init__(self, app):
        super().__init__("현금흐름 기록", "결제 직후 항목과 금액만 입력해도 종류·카테고리·계획 여부가 자동 분류됩니다. "
                                    "분류를 바꾸면 같은 항목명은 다음부터 바꾼 분류로 기록됩니다.")
        self.app = app
        self.editing = None
        k = QHBoxLayout()
        self.k_spent, self.k_left, self.k_today, self.k_count = (kpi("이번 기간 소비지출"), kpi("기간 변동예산 잔여"),
                                                                  kpi("오늘 지출"), kpi("기록 건수"))
        for w in (self.k_spent, self.k_left, self.k_today, self.k_count):
            k.addWidget(w)
        w = QWidget()
        w.setLayout(k)
        k.setContentsMargins(0, 0, 0, 0)
        self.add(w)

        f, v = card("기록 입력")
        self.form_title = f
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.item = QLineEdit()
        self.item.setPlaceholderText("지출 항목 (예: 학식, 스타벅스, 버스, 용돈)")
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("금액")
        self.method = QComboBox()
        self.method.addItems(core.METHODS)
        self.kind = QComboBox()
        self.kind.addItems(core.KINDS)
        self.cat = QComboBox()
        self.cat.setEditable(False)
        self.sub = QLineEdit()
        self.sub.setPlaceholderText("세부")
        self.planned = QComboBox()
        self.planned.addItems(["계획", "비계획"])
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("이유·상황 (예: 수업 사이 점심, 친구와 동행)")
        self.emotion = QLineEdit()
        self.emotion.setPlaceholderText("감정 (지출 후 느낌, 대체 가능성)")
        self.sat = QComboBox()
        self.sat.addItems(["5 매우 만족", "4 만족", "3 보통", "2 불만족", "1 매우 불만족"])
        self.sat.setCurrentIndex(2)
        self.receipt = ""
        self.rbtn = button("증빙 첨부", None, self.pick_receipt)
        self.auto = QLabel()
        self.auto.setObjectName("chip")
        widgets = [("날짜", self.date), ("지출 항목", self.item), ("금액", self.amount), ("결제수단", self.method),
                   ("종류", self.kind), ("카테고리", self.cat), ("세부", self.sub), ("계획 여부", self.planned),
                   ("이유·상황", self.reason), ("감정", self.emotion), ("만족도", self.sat), ("증빙", self.rbtn)]
        for i, (lab, w) in enumerate(widgets):
            r, c = divmod(i, 4)
            box = QVBoxLayout()
            box.setSpacing(3)
            l = QLabel(lab)
            l.setObjectName("hint")
            box.addWidget(l)
            box.addWidget(w)
            g.addLayout(box, r, c)
        v.addLayout(g)
        h = QHBoxLayout()
        h.addWidget(self.auto)
        h.addStretch()
        self.cancel_btn = button("취소", None, self.reset_form)
        self.cancel_btn.hide()
        self.save_btn = button("기록 추가  ⏎", "primary", self.submit)
        h.addWidget(self.cancel_btn)
        h.addWidget(self.save_btn)
        v.addLayout(h)
        self.add(f)
        self.kind.currentTextChanged.connect(self.kind_changed)
        self.item.textChanged.connect(self.auto_classify)
        for w in (self.item, self.amount, self.reason, self.emotion):
            w.returnPressed.connect(self.submit)
        self.kind_changed(self.kind.currentText())

        f, v = card("기록 목록", "행을 더블클릭하면 수정, 선택 후 삭제할 수 있습니다.")
        self.seg = QButtonGroup(self)
        for i, (key, lab) in enumerate((("month", "전체"), ("p1", "상반기"), ("p2", "후반기"))):
            b = button(lab, "seg")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.key = key
            self.seg.addButton(b)
            f.head.addWidget(b)
        self.seg.buttonClicked.connect(lambda *_: self.refresh())
        f.head.addSpacing(12)
        f.head.addWidget(button("선택 삭제", "danger", self.delete))
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(["날짜", "종류", "지출 항목", "금액", "카테고리", "세부", "결제수단", "계획",
                                              "이유·상황", "감정", "만족", "판단"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(420)
        hh = self.table.horizontalHeader()
        for i in range(12):
            hh.setSectionResizeMode(i, QHeaderView.Stretch if i in (2, 8, 9) else QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self.load_row)
        v.addWidget(self.table)
        self.add(f)
        self.finish()
        self.auto_classify()
        self.refresh()

    def kind_changed(self, kind):
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItems({"수입": ["수입"], "저축": ["저축"]}.get(kind, ["고정지출"] + core.VAR_CATS))
        self.cat.blockSignals(False)

    def auto_classify(self):
        if self.editing:
            return
        D = self.app.data
        k, c, s, why = core.classify(D, self.item.text())
        self.kind.setCurrentText(k)
        self.kind_changed(k)
        self.cat.setCurrentText(c)
        self.sub.setText(s)
        day = self.date.date().toString("yyyy-MM-dd")
        self.planned.setCurrentIndex(0 if core.guess_planned(D, k, c, s, day) else 1)
        self.auto.setText(f"자동 분류 → {k} · {c} · {s}" + (f"  ({why})" if why else "")
                          if self.item.text().strip() else "항목을 입력하면 자동 분류됩니다")

    def pick_receipt(self):
        p, _ = QFileDialog.getOpenFileName(self, "증빙 이미지 선택", str(Path.home()),
                                           "이미지 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if p:
            self.receipt = p
            self.rbtn.setText("✓ " + Path(p).name[:14])

    def submit(self):
        D = self.app.data
        item, amt = self.item.text().strip(), core.parse_amount(self.amount.text())
        if not item or amt <= 0:
            QMessageBox.information(self, "입력 확인", "지출 항목과 금액을 입력하세요.")
            return
        day = self.date.date().toPython()
        if not core.period_of(D, day):
            if QMessageBox.question(self, "기간 확인", "기록 기간 밖의 날짜입니다. 그래도 저장할까요?") != QMessageBox.Yes:
                return
        k, c, s, _ = core.classify(D, item)
        kind, cat, sub = self.kind.currentText(), self.cat.currentText(), self.sub.text().strip() or cat
        if (kind, cat, sub) != (k, c, s):
            core.learn(D, item, kind, cat, sub)
        tx = core.new_tx(D, day, item, amt, self.method.currentText(), self.reason.text().strip(),
                         self.emotion.text().strip(), int(self.sat.currentText()[0]), self.receipt,
                         kind, cat, sub, self.planned.currentIndex() == 0)
        if self.editing:
            old = next(t for t in D["transactions"] if t["id"] == self.editing)
            tx["id"], tx["judge"] = old["id"], old.get("judge", "")
            if not self.receipt:
                tx["receipt"] = old.get("receipt", "")
            D["transactions"][D["transactions"].index(old)] = tx
        else:
            D["transactions"].append(tx)
        self.reset_form()
        self.refresh()
        self.app.changed()

    def reset_form(self):
        self.editing = None
        for w in (self.item, self.amount, self.reason, self.emotion):
            w.clear()
        self.receipt = ""
        self.rbtn.setText("증빙 첨부")
        self.sat.setCurrentIndex(2)
        self.save_btn.setText("기록 추가  ⏎")
        self.cancel_btn.hide()
        self.auto_classify()
        self.item.setFocus()

    def load_row(self, r, _c):
        tid = self.table.item(r, 0).data(Qt.UserRole)
        t = next(x for x in self.app.data["transactions"] if x["id"] == tid)
        self.editing = tid
        self.date.setDate(QDate.fromString(t["date"], "yyyy-MM-dd"))
        self.item.setText(t["item"])
        self.amount.setText(core.won(t["amount"]))
        self.method.setCurrentText(t["method"])
        self.kind.setCurrentText(t["kind"])
        self.kind_changed(t["kind"])
        self.cat.setCurrentText(t["category"])
        self.sub.setText(t["sub"])
        self.planned.setCurrentIndex(0 if t["planned"] else 1)
        self.reason.setText(t["reason"])
        self.emotion.setText(t["emotion"])
        self.sat.setCurrentIndex(5 - int(t.get("satisfaction", 3)))
        self.rbtn.setText("✓ 첨부됨" if t.get("receipt") else "증빙 첨부")
        self.save_btn.setText("수정 저장")
        self.cancel_btn.show()
        self.auto.setText("기록 수정 중")

    def delete(self):
        rows = sorted({ix.row() for ix in self.table.selectedIndexes()})
        if not rows:
            return
        if QMessageBox.question(self, "삭제", f"{len(rows)}건을 삭제할까요?") != QMessageBox.Yes:
            return
        ids = {self.table.item(r, 0).data(Qt.UserRole) for r in rows}
        D = self.app.data
        D["transactions"] = [t for t in D["transactions"] if t["id"] not in ids]
        self.refresh()
        self.app.changed()

    def refresh(self):
        D = self.app.data
        key = self.seg.checkedButton().key if self.seg.checkedButton() else "month"
        txs = sorted(core.txs_in(D, key), key=lambda t: t["date"], reverse=True)
        self.table.setRowCount(0)
        for t in txs:
            i = self.table.rowCount()
            self.table.insertRow(i)
            vals = [t["date"][5:].replace("-", "/"), t["kind"], t["item"], core.won(t["amount"]), t["category"],
                    t["sub"], t["method"], "계획" if t["planned"] else "비계획", t["reason"], t["emotion"],
                    str(t.get("satisfaction", "")), core.judge_of(t)]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 0:
                    it.setData(Qt.UserRole, t["id"])
                if t["kind"] != "지출":
                    it.setForeground(Qt.darkBlue)
                self.table.setItem(i, j, it)
        today = date.today()
        cur = core.period_of(D, today) or "p1"
        an = core.analyze(D, cur)
        var_b = sum(r[2] for r in an["rows"] if r[0] == "변동지출")
        var_a = sum(r[3] for r in an["rows"] if r[0] == "변동지출")
        self.k_spent.value.setText(f"{core.won(an['expense'])}원")
        self.k_left.value.setText(f"{core.won(var_b - var_a)}원")
        self.k_left.value.setStyleSheet("color:#B91C1C" if var_b - var_a < 0 else "")
        self.k_today.value.setText(f"{core.won(sum(t['amount'] for t in D['transactions'] if t['kind'] == '지출' and t['date'] == today.isoformat()))}원")
        self.k_count.value.setText(f"{len(core.txs_in(D, 'month'))}건")
        self.k_spent.findChild(QLabel, "kpiLabel").setText(f"{core.PERIOD_LABEL[cur]} 소비지출")


class SettlePage(Page):
    def __init__(self, app):
        super().__init__("결산", "기간 예산과 실제 흐름을 비교합니다. 비고를 비워 두면 기록에서 산출한 문구가 들어가며, "
                               "직접 입력하면 그 내용이 우선합니다.")
        self.app = app
        f, v = card()
        h = QHBoxLayout()
        self.seg = QButtonGroup(self)
        for i, key in enumerate(("p1", "p2", "month")):
            b = button(core.PERIOD_LABEL[key], "seg")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.key = key
            self.seg.addButton(b)
            h.addWidget(b)
        h.addStretch()
        h.addWidget(QLabel("기간 말 실제 잔액(가용 현금)"))
        self.actual = QLineEdit()
        self.actual.setPlaceholderText("계좌·현금 실제 합계")
        self.actual.setFixedWidth(170)
        self.actual.editingFinished.connect(self.save_actual)
        h.addWidget(self.actual)
        v.addLayout(h)
        self.add(f)
        self.seg.buttonClicked.connect(lambda *_: self.refresh())
        k = QHBoxLayout()
        self.kp = {n: kpi(n) for n in ("유입", "유출", "순현금흐름", "예비비 사용", "최저 잔액", "장부 vs 실제")}
        for w in self.kp.values():
            k.addWidget(w)
        w = QWidget()
        w.setLayout(k)
        k.setContentsMargins(0, 0, 0, 0)
        self.add(w)
        f, v = card("예산 대비 실적")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["구분", "항목", "기간 예산", "실제 흐름", "차이", "비고"])
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(430)
        hh = self.table.horizontalHeader()
        for i in range(6):
            hh.setSectionResizeMode(i, QHeaderView.Stretch if i == 5 else QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self.remark_edit)
        v.addWidget(self.table)
        self.add(f)
        row = QHBoxLayout()
        f, v = card("차이 해석", "합계 차이뿐 아니라 원인(일정, 감정, 동행, 피로 등)과 다음 행동을 함께 적습니다.")
        self.facts = QLabel()
        self.facts.setObjectName("hint")
        self.facts.setWordWrap(True)
        v.addWidget(self.facts)
        self.interp = QPlainTextEdit()
        self.interp.setMinimumHeight(140)
        self.interp.textChanged.connect(self.save_interp)
        v.addWidget(self.interp)
        row.addWidget(f, 1)
        f, v = card("변동지출 예산 대비 실적")
        self.chart = QLabel()
        self.chart.setAlignment(Qt.AlignCenter)
        self.chart.setMinimumHeight(260)
        v.addWidget(self.chart)
        row.addWidget(f, 1)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.add(w)
        self.finish()

    def key(self):
        return self.seg.checkedButton().key

    def refresh(self):
        D = self.app.data
        key = self.key()
        an = core.analyze(D, key)
        self._filling = True
        self.table.setRowCount(0)
        for g, n, b, a in an["rows"]:
            i = self.table.rowCount()
            self.table.insertRow(i)
            user = D["settle"][key].get("remarks", {}).get(f"{g}|{n}", "")
            vals = [g, n, core.won(b), core.won(a), f"{a - b:+,}" if a - b else "0", user]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j in (2, 3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j != 5:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setToolTip(core.auto_remark(an, g, n))
                    if not user:
                        it.setData(Qt.UserRole, "auto")
                        it.setText("")
                if j == 4 and a != b:
                    bad = (a < b) if g == "소득" else (a > b)
                    it.setForeground(Qt.red if bad else Qt.darkGreen)
                self.table.setItem(i, j, it)
            auto = core.auto_remark(an, g, n)
            if not user and auto:
                self.table.item(i, 5).setText("")
                self.table.item(i, 5).setToolTip(auto)
                ph = QTableWidgetItem(auto)
                ph.setForeground(Qt.gray)
                ph.setData(Qt.UserRole, "auto")
                self.table.setItem(i, 5, ph)
        self._filling = False
        self.kp["유입"].value.setText(core.won(an["inflow_a"]))
        self.kp["유출"].value.setText(core.won(an["out_a"]))
        self.kp["순현금흐름"].value.setText(f"{an['net_a']:+,}")
        self.kp["예비비 사용"].value.setText(f"{core.won(an['reserve_used'])} / {core.won(an['reserve_b'])}")
        self.kp["최저 잔액"].value.setText(f"{core.won(an['min_bal'])} ({an['min_day'].month}/{an['min_day'].day})")
        ae = an["actual_end"]
        self.kp["장부 vs 실제"].value.setText("미입력" if ae is None else
                                         "일치" if ae == an["book_end"] else f"{an['book_end'] - ae:+,}")
        self.actual.setText("" if ae is None else core.won(ae))
        self.actual.setPlaceholderText(f"장부 {core.won(an['book_end'])}원")
        self.interp.blockSignals(True)
        self.interp.setPlainText(D["settle"][key].get("interpret", ""))
        self.interp.blockSignals(False)
        from .export_docx import _facts
        fs = _facts(an)
        self.facts.setText("\n".join("· " + x for x in fs) if fs else "차이가 있는 변동지출 항목이 없습니다.")
        pm = QPixmap()
        pm.loadFromData(charts.budget_vs_actual(an).getvalue())
        self.chart.setPixmap(pm.scaledToWidth(520, Qt.SmoothTransformation))

    def remark_edit(self, it):
        if getattr(self, "_filling", False) or it.column() != 5:
            return
        D = self.app.data
        r = it.row()
        k = f"{self.table.item(r, 0).text()}|{self.table.item(r, 1).text()}"
        rem = D["settle"][self.key()].setdefault("remarks", {})
        if it.data(Qt.UserRole) == "auto":
            it.setData(Qt.UserRole, None)
            it.setForeground(Qt.black)
        if it.text().strip():
            rem[k] = it.text().strip()
        else:
            rem.pop(k, None)
        self.app.changed()

    def save_actual(self):
        t = self.actual.text().strip()
        self.app.data["settle"][self.key()]["actual_end"] = core.parse_amount(t) if t else None
        self.app.changed()
        self.refresh()

    def save_interp(self):
        self.app.data["settle"][self.key()]["interpret"] = self.interp.toPlainText()
        self.app.changed()


class EvalPage(Page):
    def __init__(self, app):
        super().__init__("평가 · 원칙", "분석의 한계, 절약 목표와 실행 방안, 느낀 점과 나만의 현금흐름 관리 원칙을 정리합니다.")
        self.app = app
        E = app.data["evaluation"]
        f, v = card("분석의 한계", "해당하는 항목을 선택하고 구체적으로 설명합니다.")
        self.checks = []
        g = QGridLayout()
        for i, t in enumerate(core.LIMIT_TYPES):
            c = QCheckBox(t)
            c.setChecked(t in E["limits"])
            c.toggled.connect(self.sync)
            self.checks.append(c)
            g.addWidget(c, i // 2, i % 2)
        v.addLayout(g)
        self.limit = QPlainTextEdit(E.get("limit_text", ""))
        self.limit.setPlaceholderText("예: 이번 기록에 포함되지 않은 지출과 그 이유, 결과 해석 시 유의할 점")
        self.limit.setMinimumHeight(100)
        self.limit.textChanged.connect(self.sync)
        v.addWidget(self.limit)
        self.add(f)
        f, self.goals = table_block(
            "절약 목표와 실행 방안", "목표에는 금액·행동·기간·점검 방법을 포함합니다. '결산 기반 초안'은 상반기 기록에서 "
            "예산 초과·비계획 비중이 큰 항목을 골라 채우며, 반드시 검토 후 수정합니다.",
            [("problem", "발견한 문제", "text"), ("target", "목표", "text"), ("action", "행동", "text"),
             ("saving", "예상 조정액", "text"), ("check", "점검 방법", "text"), ("use", "절약액의 용도", "text")],
            E["goals"], self.sync, 200)
        f.head.insertWidget(2, button("결산 기반 초안", "ghost", self.draft))
        self.add(f)
        f, v = card("느낀 점")
        self.feel = QPlainTextEdit(E.get("feelings", ""))
        self.feel.setMinimumHeight(130)
        self.feel.textChanged.connect(self.sync)
        v.addWidget(self.feel)
        self.add(f)
        f, self.prin = table_block(
            "나의 현금흐름 관리 원칙", "기록에서 발견한 문제와 연결되고, 행동이 구체적이며, 실천 여부를 확인할 수 있는 원칙으로 작성합니다.",
            [("principle", "원칙", "text"), ("check", "실천 확인 방법", "text")], E.get("principles", []),
            self.sync, 200)
        self.add(f)
        self.finish()

    def sync(self, *_):
        E = self.app.data["evaluation"]
        E["limits"] = [c.text() for c in self.checks if c.isChecked()]
        E["limit_text"] = self.limit.toPlainText()
        E["goals"] = self.goals.rows()
        E["feelings"] = self.feel.toPlainText()
        E["principles"] = self.prin.rows()
        self.app.changed()

    def draft(self):
        ds = core.goal_drafts(self.app.data)
        if not ds:
            QMessageBox.information(self, "초안", "상반기 기록에서 예산 초과나 비계획 지출이 확인되지 않았습니다.")
            return
        for g in ds:
            self.goals.add_row(g)
        self.sync()


class Worker(QObject):
    log = Signal(str)
    done = Signal(object, str)

    def __init__(self, data, out):
        super().__init__()
        self.data, self.out = data, out

    def run(self):
        try:
            res = report.generate(self.data, self.out, self.log.emit)
            self.done.emit(res, "")
        except Exception as e:
            self.done.emit(None, str(e))


class ExportPage(Page):
    def __init__(self, app):
        super().__init__("보고서 출력", "Excel 부속명세서와 Word 보고서를 만든 뒤 PDF로 변환해 하나의 제출용 파일로 묶습니다. "
                                   "PDF 변환에는 MS Office(Word·Excel) 또는 LibreOffice가 필요합니다.")
        self.app = app
        f, v = card("출력 위치")
        h = QHBoxLayout()
        self.out = QLineEdit(str(DATA_DIR / "출력"))
        h.addWidget(self.out, 1)
        h.addWidget(button("변경", None, self.pick))
        h.addWidget(button("폴더 열기", None, self.open_dir))
        v.addLayout(h)
        self.add(f)
        f, v = card("제출 전 확인")
        self.miss = QLabel()
        self.miss.setWordWrap(True)
        v.addWidget(self.miss)
        self.add(f)
        f, v = card()
        self.go = button("보고서 생성 (Excel · Word · PDF)", "primary", self.run)
        self.go.setMinimumHeight(44)
        v.addWidget(self.go)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMinimumHeight(160)
        v.addWidget(self.logbox)
        self.add(f)
        self.finish()

    def refresh(self):
        m = report.missing(self.app.data)
        self.miss.setText("입력이 필요한 항목\n· " + "\n· ".join(m) if m else "필수 항목이 모두 입력되었습니다.")
        self.miss.setObjectName("warn" if m else "ok")
        self.miss.setStyleSheet("")

    def pick(self):
        p = QFileDialog.getExistingDirectory(self, "출력 폴더", self.out.text())
        if p:
            self.out.setText(p)

    def open_dir(self):
        p = Path(self.out.text())
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)])

    def run(self):
        self.app.save_now()
        if report.missing(self.app.data) and QMessageBox.question(
                self, "확인", "입력되지 않은 항목이 있습니다. 그대로 생성할까요?") != QMessageBox.Yes:
            return
        self.go.setEnabled(False)
        self.logbox.clear()
        self.thread = QThread()
        self.worker = Worker(self.app.data, self.out.text())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.logbox.appendPlainText)
        self.worker.done.connect(self.finished)
        self.thread.start()

    def finished(self, res, err):
        self.thread.quit()
        self.thread.wait()
        self.go.setEnabled(True)
        if err:
            self.logbox.appendPlainText("오류: " + err)
            QMessageBox.critical(self, "생성 실패", err)
        else:
            if sys.platform == "win32":
                os.startfile(res["pdf"])


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("현금흐름 관리")
        self.resize(1360, 860)
        self.data = core.load(DATA_FILE)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.save_now)
        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 12)
        sv.setSpacing(2)
        b = QLabel("Cash Flow")
        b.setObjectName("brand")
        s = QLabel("개인 현금흐름 관리")
        s.setObjectName("brandSub")
        sv.addWidget(b)
        sv.addWidget(s)
        self.stack = QStackedWidget()
        self.pages = [SetupPage(self), BudgetPage(self), RecordPage(self), SettlePage(self), EvalPage(self),
                      ExportPage(self)]
        names = ["기본 정보", "예산 수립", "기록", "결산", "평가 · 원칙", "보고서 출력"]
        self.nav = QButtonGroup(self)
        for i, (n, p) in enumerate(zip(names, self.pages)):
            self.stack.addWidget(p)
            bt = button(f"{i + 1:02d}   {n}", "nav")
            bt.setCheckable(True)
            bt.setChecked(i == 0)
            self.nav.addButton(bt, i)
            sv.addWidget(bt)
        sv.addStretch()
        self.saved = QLabel("")
        self.saved.setStyleSheet("color:#64748B; font-size:11px; padding: 0 20px;")
        sv.addWidget(self.saved)
        self.nav.idClicked.connect(self.go)
        lay.addWidget(side)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        start = 2 if self.data["budget"].get("choice") else 0
        self.nav.button(start).setChecked(True)
        self.go(start)

    def go(self, i):
        self.save_now()
        p = self.pages[i]
        if hasattr(p, "refresh") and not isinstance(p, SetupPage):
            p.refresh()
        if isinstance(p, BudgetPage):
            p.compute(silent=True)
            p.fill_budget()
        self.stack.setCurrentIndex(i)

    def changed(self):
        self._timer.start(600)

    def save_now(self):
        core.save(self.data, DATA_FILE)
        self.saved.setText("자동 저장 " + datetime.now().strftime("%H:%M:%S"))

    def closeEvent(self, e):
        self.save_now()
        e.accept()


def run():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    app.setFont(QFont("Malgun Gothic", 10))
    w = Main()
    w.show()
    sys.exit(app.exec())
