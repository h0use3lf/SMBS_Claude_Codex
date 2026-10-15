"""데이터 모델, 자동 분류, 예산 산출, 2주 분할, 결산 분석."""
import calendar
import json
import math
import re
import uuid
from datetime import date, timedelta
from pathlib import Path

VAR_CATS = ["식비", "카페·간식", "교통비", "학업·생활용품", "쇼핑·의류", "여가·모임", "기타"]
DEFAULT_WEIGHTS = {"식비": 40, "카페·간식": 10, "교통비": 15, "학업·생활용품": 12,
                   "쇼핑·의류": 8, "여가·모임": 15, "기타": 0}
# 평일 1일 대비 휴일(주말·공휴일) 1일의 소비 가중치
DAY_WEIGHTS = {"식비": (1.0, 1.0), "카페·간식": (1.0, 0.7), "교통비": (1.0, 0.2),
               "학업·생활용품": (1.0, 0.5), "쇼핑·의류": (1.0, 1.0), "여가·모임": (0.6, 1.5),
               "기타": (1.0, 1.0)}
METHODS = ["체크카드", "신용카드", "현금", "계좌이체", "간편결제"]
KINDS = ["지출", "수입", "저축"]
JUDGE = ["유지", "조정", "중단"]
ASSET_TYPES = ["유동자산", "저축자산", "부채"]
LIMIT_TYPES = [
    "고정비(월세·통신비 등) 납부일이 기록 기간에 없었음",
    "시험·여행·명절 등 특별한 일정이 있었음",
    "병원비·교재비 등 일회성 지출이 있었음",
    "용돈·아르바이트비 입금일이 기록 기간에 포함되지 않음",
    "기록하지 못했거나 정확히 기억나지 않는 지출이 있음",
    "부모님이나 친구가 대신 지출한 경우가 있음",
]
TIERS = {
    "A": {"name": "보수안", "keep": 1.0, "reserve": 0.10,
          "desc": "이번 달 수입 범위 안에서만 생활하고 이월 잔액은 전액 보존"},
    "B": {"name": "균형안", "keep": 0.5, "reserve": 0.10,
          "desc": "이월 잔액의 50%를 생활비로 활용하고 50%는 보존"},
    "C": {"name": "적극안", "keep": 0.2, "reserve": 0.10,
          "desc": "이월 잔액의 80%까지 활용, 20%는 최소 안전자금으로 보존"},
}

# (키워드, 종류, 카테고리, 세부항목) — 앞쪽 규칙이 우선
RULES = [
    (["용돈"], "수입", "수입", "용돈"),
    (["급여", "월급", "알바비", "아르바이트", "주급"], "수입", "수입", "아르바이트 급여"),
    (["장학금"], "수입", "수입", "장학금"),
    (["환급", "이자", "캐시백", "중고판매", "당근판매"], "수입", "수입", "기타 수입"),
    (["청약"], "저축", "저축", "청약저축"),
    (["적금", "예금", "저축", "비상금", "투자", "주식", "etf", "펀드"], "저축", "저축", "적금·투자"),
    (["배달", "배민", "요기요", "쿠팡이츠"], "지출", "식비", "배달"),
    (["학식", "학생식당", "구내식당", "기숙사식당", "교직원식당"], "지출", "식비", "학식"),
    (["마트", "장보기", "이마트", "홈플러스", "식자재"], "지출", "식비", "장보기"),
    (["편의점", "cu", "gs25", "세븐일레븐", "이마트24", "미니스톱"], "지출", "카페·간식", "편의점"),
    (["카페", "커피", "스타벅스", "메가커피", "컴포즈", "이디야", "투썸", "빽다방", "음료",
      "라떼", "아메리카노", "디저트", "베이커리", "빵", "과자", "간식", "아이스크림", "탕후루"],
     "지출", "카페·간식", "카페·간식"),
    (["택시", "카카오t"], "지출", "교통비", "택시"),
    (["버스", "지하철", "교통", "기차", "ktx", "srt", "고속버스", "시외버스", "따릉이",
      "킥보드", "주유", "톨게이트"], "지출", "교통비", "대중교통"),
    (["교재", "전공책", "책", "문구", "프린트", "인쇄", "복사", "노트", "펜", "토익", "응시료",
      "원서", "강의", "인강", "학원"], "지출", "학업·생활용품", "학업"),
    (["다이소", "올리브영", "생필품", "세제", "휴지", "샴푸", "화장품", "약국", "약", "치약"],
     "지출", "학업·생활용품", "생활용품"),
    (["옷", "의류", "신발", "무신사", "지그재그", "에이블리", "29cm", "유니클로", "쿠팡"],
     "지출", "쇼핑·의류", "쇼핑"),
    (["술", "호프", "주점", "회식", "뒷풀이", "뒤풀이", "모임", "생일", "선물", "축의"],
     "지출", "여가·모임", "모임"),
    (["영화", "cgv", "메가박스", "롯데시네마", "노래방", "pc방", "피시방", "게임", "공연", "전시",
      "여행", "볼링", "당구", "숙소"], "지출", "여가·모임", "여가"),
    (["식당", "밥", "점심", "저녁", "아침", "국밥", "김밥", "라면", "치킨", "피자", "버거",
      "맥도날드", "롯데리아", "버거킹", "분식", "떡볶이", "고기", "마라탕", "돈까스", "초밥",
      "식사", "외식", "냉면", "짜장", "짬뽕", "찌개", "덮밥", "샌드위치", "서브웨이"],
     "지출", "식비", "외식"),
]
ROUTINE_SUBS = {"학식", "대중교통"}


def norm(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


def parse_amount(v):
    if isinstance(v, (int, float)):
        return int(v)
    s = re.sub(r"[^\d\-]", "", str(v or ""))
    return int(s) if s not in ("", "-") else 0


def won(v):
    return f"{int(round(v)):,}"


def d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s))


# ───────────────────────────── 데이터 ─────────────────────────────
def default_data():
    return {
        "profile": {"title": "나의 돈 흐름을 이해하고, 소비 습관 바꾸기", "course": "", "dept": "",
                    "student_id": "", "name": "", "submit_date": "",
                    "life_type": "", "income_sources": "", "managed": "", "cost_split": ""},
        "period": {"start": "2026-10-01", "split_days": 14},
        "holidays": ["2026-10-03", "2026-10-05", "2026-10-09"],
        "assets": [],          # {name, type, start, end}
        "incomes": [],         # {name, amount, date, basis}
        "savings": [],         # {name, amount, date, basis}
        "fixed": [],           # {name, amount, date, basis}
        "family_paid": [],     # {name, amount, payer, note}
        "events": [],          # {date, category, amount, note}
        "history": {"start": "", "balance": "", "rows": []},  # rows: {date, item, amount, category}
        "weights": dict(DEFAULT_WEIGHTS),
        "budget": {"choice": "", "variable": {}, "reserve": 0, "basis": {}},
        "transactions": [],
        "learned": {},
        "settle": {"p1": {"actual_end": None, "remarks": {}},
                   "p2": {"actual_end": None, "remarks": {}},
                   "month": {"actual_end": None, "remarks": {}}},
        "evaluation": {"limits": [], "limit_text": "", "goals": [], "feelings": "", "principles": []},
    }


def load(path):
    p = Path(path)
    base = default_data()
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        for k, v in base.items():
            data.setdefault(k, v)
        for k in ("p1", "p2", "month"):
            data["settle"].setdefault(k, {"actual_end": None, "remarks": {}})
        return data
    return base


def save(data, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ───────────────────────────── 기간 ─────────────────────────────
def periods(data):
    s = d(data["period"]["start"])
    last = calendar.monthrange(s.year, s.month)[1]
    month_end = date(s.year, s.month, last) if s.day == 1 else (
        date(s.year + (s.month // 12), s.month % 12 + 1, s.day) - timedelta(days=1))
    p1_end = s + timedelta(days=int(data["period"].get("split_days", 14)) - 1)
    return {"p1": (s, p1_end), "p2": (p1_end + timedelta(days=1), month_end), "month": (s, month_end)}


PERIOD_LABEL = {"p1": "상반기", "p2": "후반기", "month": "월 전체"}


def period_title(data, key):
    a, b = periods(data)[key]
    return f"{PERIOD_LABEL[key]}({a.month}/{a.day}~{b.month}/{b.day})"


def days_in(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def is_holiday(data, day):
    return day.weekday() >= 5 or day.isoformat() in set(data.get("holidays", []))


def period_of(data, day):
    day = d(day)
    for k in ("p1", "p2"):
        a, b = periods(data)[k]
        if a <= day <= b:
            return k
    return None


# ───────────────────────────── 자동 분류 ─────────────────────────────
def classify(data, item):
    """항목명 → (종류, 카테고리, 세부항목, 판단근거)."""
    key = norm(item)
    if not key:
        return "지출", "기타", "기타", ""
    if key in data.get("learned", {}):
        k, c, s = data["learned"][key]
        return k, c, s, "학습된 분류"
    for kind, lst, cat in (("지출", data["fixed"], "고정지출"), ("저축", data["savings"], "저축"),
                           ("수입", data["incomes"], "수입")):
        for p in lst:
            pn = norm(p.get("name"))
            if pn and (pn in key or key in pn):
                return kind, cat, p["name"], "계획 항목 일치"
    for kws, kind, cat, sub in RULES:
        for kw in kws:
            if kw in key:
                return kind, cat, sub, f"키워드 '{kw}'"
    return "지출", "기타", "기타", "규칙 없음"


def learn(data, item, kind, cat, sub):
    data.setdefault("learned", {})[norm(item)] = [kind, cat, sub]


def guess_planned(data, kind, cat, sub, day):
    if kind in ("수입", "저축") or cat == "고정지출":
        return True
    for e in data["events"]:
        if e.get("category") == cat and e.get("date") == str(day):
            return True
    return sub in ROUTINE_SUBS


def auto_judge(tx):
    s = int(tx.get("satisfaction") or 3)
    if tx.get("kind") != "지출":
        return "유지"
    if s >= 4:
        return "유지"
    if s <= 2 and not tx.get("planned"):
        return "중단"
    if not tx.get("planned") or tx.get("sub") in ("배달", "카페·간식", "편의점", "택시"):
        return "조정"
    return "유지"


def judge_of(tx):
    return tx.get("judge") or auto_judge(tx)


def new_tx(data, day, item, amount, method="체크카드", reason="", emotion="", satisfaction=3,
           receipt="", kind=None, category=None, sub=None, planned=None):
    k, c, s, _ = classify(data, item)
    kind, category, sub = kind or k, category or c, sub or s
    if planned is None:
        planned = guess_planned(data, kind, category, sub, day)
    return {"id": uuid.uuid4().hex[:10], "date": str(day), "kind": kind, "item": item,
            "amount": parse_amount(amount), "category": category, "sub": sub, "method": method,
            "planned": bool(planned), "reason": reason, "emotion": emotion,
            "satisfaction": int(satisfaction), "receipt": receipt, "judge": ""}


# ───────────────────────────── 예산 ─────────────────────────────
def start_liquid(data):
    a = sum(parse_amount(x.get("start")) for x in data["assets"] if x.get("type") == "유동자산")
    l = sum(parse_amount(x.get("start")) for x in data["assets"] if x.get("type") == "부채")
    return a - l


def plan_sum(lst):
    return sum(parse_amount(x.get("amount")) for x in lst)


def round_alloc(total, weights, unit=1000):
    """가중치 비례 배분 — 단위 절사 후 최대잔여법으로 합계 일치."""
    tw = sum(weights.values())
    if tw <= 0 or total <= 0:
        return {k: 0 for k in weights}
    units = total // unit
    raw = {k: units * w / tw for k, w in weights.items()}
    base = {k: int(math.floor(v)) for k, v in raw.items()}
    rest = units - sum(base.values())
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)[:rest]:
        base[k] += 1
    out = {k: v * unit for k, v in base.items()}
    first = max(weights, key=weights.get)
    out[first] += total - units * unit
    return out


# ───────────────────────────── 지난 기록 역산 ─────────────────────────────
HIST_CATS = ["자동", "수입", "저축", "고정지출"] + VAR_CATS
HIST_ASSET = "가용 현금(지난 기록 역산)"


def history_txs(data):
    """지난 기록 행 → 분류된 거래 목록. 분류가 '자동'이면 classify 결과 사용. 날짜 오류 행은 제외."""
    out, bad = [], 0
    for r in data["history"].get("rows", []):
        if not str(r.get("item", "")).strip():
            continue
        try:
            dt = d(r.get("date"))
        except (TypeError, ValueError):
            bad += 1
            continue
        cat = r.get("category") or "자동"
        if cat == "자동":
            kind, cat, sub, _ = classify(data, r["item"])
        else:
            kind, sub = {"수입": "수입", "저축": "저축"}.get(cat, "지출"), r["item"]
        out.append({"date": dt, "item": r["item"], "amount": parse_amount(r.get("amount")),
                    "kind": kind, "category": cat, "sub": sub})
    return sorted(out, key=lambda t: t["date"]), bad


def derive_history(data):
    """지정한 시작점(날짜·잔액)과 지난 기록으로 기초 잔액·배분 비율·수입/저축/고정지출 계획 역산."""
    h = data["history"]
    if not h.get("start"):
        return None
    a, ms = d(h["start"]), periods(data)["month"][0]
    txs, bad = history_txs(data)
    used = [t for t in txs if a <= t["date"] < ms]
    s = lambda kind: sum(t["amount"] for t in used if t["kind"] == kind)
    var = {c: sum(t["amount"] for t in used if t["kind"] == "지출" and t["category"] == c) for c in VAR_CATS}
    last = calendar.monthrange(ms.year, ms.month)[1]
    plans = {"incomes": {}, "savings": {}, "fixed": {}}
    for t in used:
        key = {"수입": "incomes", "저축": "savings"}.get(t["kind"], "fixed" if t["category"] == "고정지출" else None)
        if key:
            # shortcut: 월 1회 항목으로 보고 마지막 금액·같은 날짜로 반영, 주 단위 반복 항목은 사용자가 수정
            day = date(ms.year, ms.month, min(t["date"].day, last))
            plans[key][t["sub"]] = {"name": t["sub"], "amount": t["amount"], "date": day.isoformat(),
                                    "basis": f"지난 기록 {t['date'].month}/{t['date'].day} {won(t['amount'])}원 기준"}
    return {
        "range": (a, ms - timedelta(days=1)), "days": (ms - a).days, "count": len(used),
        "outside": len(txs) - len(used), "bad": bad,
        "income": s("수입"), "expense": s("지출"), "saving": s("저축"),
        "balance": parse_amount(h.get("balance")) + s("수입") - s("지출") - s("저축"),
        "var": var, "weights": round_alloc(100, var, unit=1) if sum(var.values()) > 0 else None,
        "plans": plans,
    }


def apply_history(data, r):
    """역산 결과를 재무상태·배분 비율·계획 표에 반영(같은 이름은 갱신, 나머지는 유지)."""
    row = next((x for x in data["assets"] if x.get("name") == HIST_ASSET), None)
    if row is None:
        row = {"name": HIST_ASSET, "type": "유동자산", "end": ""}
        data["assets"].insert(0, row)
    row["start"] = r["balance"]
    if r["weights"]:
        data["weights"] = r["weights"]
    for key, items in r["plans"].items():
        cur = {x.get("name"): x for x in data[key]}
        for name, x in items.items():
            if name in cur:
                cur[name].update(x)
            else:
                data[key].append(x)


def budget_options(data):
    """현재 자금 상태와 수입으로 가용 예산 3안 산출."""
    start = start_liquid(data)
    inc, sav, fix = plan_sum(data["incomes"]), plan_sum(data["savings"]), plan_sum(data["fixed"])
    base = inc - sav - fix
    opts = {}
    for key, t in TIERS.items():
        use_carry = int(max(start, 0) * (1 - t["keep"]))
        avail = max(base + use_carry, 0)
        reserve = int(avail * t["reserve"] // 1000 * 1000)
        variable = avail - reserve
        opts[key] = {
            "key": key, "name": t["name"], "desc": t["desc"], "available": avail,
            "variable": variable, "reserve": reserve, "carry_used": use_carry,
            "carry_end": start + base - avail,
            "saving_rate": (sav / inc * 100) if inc else 0.0,
            "daily": variable / max(len(days_in(*periods(data)["month"])), 1),
        }
    return {"start": start, "income": inc, "savings": sav, "fixed": fix, "base": base, "options": opts}


def apply_choice(data, key):
    o = budget_options(data)["options"][key]
    w = {c: float(data["weights"].get(c, 0)) for c in VAR_CATS}
    alloc = round_alloc(o["variable"], w)
    ev = event_sums(data)
    for c in VAR_CATS:  # 예정 일정 금액이 배분액보다 크면 일정 금액을 우선 보장
        need = ev.get(c, {}).get("p1", 0) + ev.get(c, {}).get("p2", 0)
        if alloc[c] < need:
            alloc[c] = need
    over = sum(alloc.values()) - o["variable"]
    if over > 0:  # 일정 보장으로 늘어난 만큼 가중치가 큰 항목에서 차감
        for c in sorted(VAR_CATS, key=lambda c: -w[c]):
            room = alloc[c] - (ev.get(c, {}).get("p1", 0) + ev.get(c, {}).get("p2", 0))
            cut = min(room, over)
            alloc[c] -= cut
            over -= cut
            if over <= 0:
                break
    data["budget"] = {"choice": key, "variable": alloc, "reserve": o["reserve"],
                      "basis": {**data["budget"].get("basis", {})}}
    return data["budget"]


def event_sums(data):
    out = {}
    for e in data["events"]:
        p = period_of(data, e.get("date"))
        if not p:
            continue
        out.setdefault(e["category"], {"p1": 0, "p2": 0})[p] += parse_amount(e.get("amount"))
    return out


def day_profile(data, key):
    a, b = periods(data)[key]
    ds = days_in(a, b)
    h = sum(1 for x in ds if is_holiday(data, x))
    return len(ds), len(ds) - h, h


def split_variable(data, cat, month_amt):
    n1, wd1, h1 = day_profile(data, "p1")
    n2, wd2, h2 = day_profile(data, "p2")
    ww, wh = DAY_WEIGHTS.get(cat, (1, 1))
    ev = event_sums(data).get(cat, {"p1": 0, "p2": 0})
    rest = max(month_amt - ev["p1"] - ev["p2"], 0)
    W1, W2 = wd1 * ww + h1 * wh, wd2 * ww + h2 * wh
    r1 = int(round(rest * W1 / (W1 + W2) / 1000) * 1000) if W1 + W2 else 0
    p1 = ev["p1"] + r1
    p2 = month_amt - p1
    basis = f"평일:휴일 가중 {ww:g}:{wh:g} 일수 배분"
    evs = [e for e in data["events"] if e.get("category") == cat and period_of(data, e.get("date"))]
    if evs:
        basis += " + 일정 " + ", ".join(
            f"{d(e['date']).month}/{d(e['date']).day} {e.get('note', '')} {won(parse_amount(e['amount']))}"
            for e in evs)
    return p1, p2, basis


def budget_rows(data):
    """[구분, 항목, 월, 상반, 후반, 설정근거, 2주 설정근거]"""
    ps = periods(data)
    rows = []
    start = start_liquid(data)
    rows.append(["소득", "기초 잔액(이월)", start, start, 0, "기초 유동자산 − 단기부채", "기록 시작일 보유"])

    def dated(group, lst):
        for x in lst:
            amt = parse_amount(x.get("amount"))
            p = period_of(data, x.get("date")) if x.get("date") else "p1"
            dt = d(x["date"]) if x.get("date") else None
            when = f"{dt.month}/{dt.day} 예정" if dt else "일자 미지정(상반기 반영)"
            rows.append([group, x.get("name", ""), amt, amt if p != "p2" else 0, amt if p == "p2" else 0,
                         x.get("basis", ""), f"{when} → {PERIOD_LABEL[p or 'p1']}"])

    dated("소득", data["incomes"])
    dated("저축", data["savings"])
    dated("고정지출", data["fixed"])
    var = data["budget"].get("variable", {})
    for c in VAR_CATS:
        m = int(var.get(c, 0))
        if m == 0 and data["weights"].get(c, 0) == 0:
            continue
        p1, p2, sb = split_variable(data, c, m)
        basis = data["budget"].get("basis", {}).get(c) or f"가중치 {data['weights'].get(c, 0):g}% 배분"
        rows.append(["변동지출", c, m, p1, p2, basis, sb])
    rv = int(data["budget"].get("reserve", 0))
    n1, _, _ = day_profile(data, "p1")
    n2, _, _ = day_profile(data, "p2")
    r1 = int(round(rv * n1 / (n1 + n2) / 1000) * 1000)
    rows.append(["예비비", "예비비", rv, r1, rv - r1,
                 data["budget"].get("basis", {}).get("예비비") or f"가용 예산의 {int(TIERS.get(data['budget'].get('choice') or 'B')['reserve']*100)}%",
                 f"기간 일수 비례({n1}일:{n2}일)"])
    return rows


def budget_summary(data):
    rows = budget_rows(data)
    g = lambda grp, i=2: sum(r[i] for r in rows if r[0] == grp)
    return {"start": rows[0][2], "income": g("소득") - rows[0][2], "savings": g("저축"),
            "fixed": g("고정지출"), "variable": g("변동지출"), "reserve": g("예비비")}


# ───────────────────────────── 결산 ─────────────────────────────
def txs_in(data, key):
    a, b = periods(data)[key]
    return sorted([t for t in data["transactions"] if a <= d(t["date"]) <= b],
                  key=lambda t: (t["date"], t.get("id", "")))


def book_start(data, key):
    s = start_liquid(data)
    if key == "p2":
        p1 = analyze(data, "p1", _nested=True)
        act = data["settle"]["p1"].get("actual_end")
        return parse_amount(act) if act not in (None, "") else p1["book_end"]
    return s


def analyze(data, key, _nested=False):
    txs = txs_in(data, key)
    col = {"p1": 3, "p2": 4, "month": 2}[key]
    rows = budget_rows(data)
    start = book_start(data, key) if not _nested else start_liquid(data)

    def act(kind, cat=None, sub=None):
        return sum(t["amount"] for t in txs if t["kind"] == kind and (cat is None or t["category"] == cat)
                   and (sub is None or t["sub"] == sub))

    var_rows = []
    known = {("소득", r[1]) for r in rows} | {("저축", r[1]) for r in rows} | {("고정지출", r[1]) for r in rows}
    for r in rows:
        grp, name, bud = r[0], r[1], r[col]
        if grp == "소득":
            a = start if name == "기초 잔액(이월)" else act("수입", sub=name)
            if name == "기초 잔액(이월)" and key == "p2":
                p1r = [r2 for r2 in rows if r2[0] != "예비비"]
                bud = sum(r2[3] for r2 in p1r if r2[0] == "소득") - sum(r2[3] for r2 in p1r if r2[0] != "소득")
        elif grp == "저축":
            a = act("저축", sub=name)
        elif grp == "고정지출":
            a = act("지출", "고정지출", name)
        elif grp == "변동지출":
            a = act("지출", name)
        else:
            continue
        var_rows.append([grp, name, bud, a])
    extra = {}
    for t in txs:
        grp = {"수입": "소득", "저축": "저축"}.get(t["kind"], "고정지출" if t["category"] == "고정지출" else None)
        if grp and (grp, t["sub"]) not in known:
            extra.setdefault((grp, t["sub"]), 0)
            extra[(grp, t["sub"])] += t["amount"]
    for (grp, name), a in extra.items():
        idx = max([i for i, r in enumerate(var_rows) if r[0] == grp], default=len(var_rows) - 1) + 1
        var_rows.insert(idx, [grp, name, 0, a])

    inflow_b = sum(r[2] for r in var_rows if r[0] == "소득")
    inflow_a = sum(r[3] for r in var_rows if r[0] == "소득")
    out_b = sum(r[2] for r in var_rows if r[0] != "소득")
    out_a = sum(r[3] for r in var_rows if r[0] != "소득")
    spend_b = sum(r[2] for r in var_rows if r[0] in ("고정지출", "변동지출"))
    spend_a = sum(r[3] for r in var_rows if r[0] in ("고정지출", "변동지출"))
    reserve_b = next((r[col] for r in rows if r[0] == "예비비"), 0)
    reserve_used = max(0, spend_a - spend_b)

    exp = [t for t in txs if t["kind"] == "지출"]
    income_tx = sum(t["amount"] for t in txs if t["kind"] == "수입")
    sav_tx = sum(t["amount"] for t in txs if t["kind"] == "저축")
    total_exp = sum(t["amount"] for t in exp)

    cats = {}
    for t in exp:
        c = cats.setdefault(t["category"], {"amount": 0, "count": 0, "subs": {}})
        c["amount"] += t["amount"]
        c["count"] += 1
        c["subs"][t["sub"]] = c["subs"].get(t["sub"], 0) + t["amount"]
    for c in cats.values():
        c["pct_exp"] = c["amount"] / total_exp * 100 if total_exp else 0
        c["pct_inc"] = c["amount"] / income_tx * 100 if income_tx else 0

    a, b = periods(data)[key]
    ds = days_in(a, b)
    wd = [x for x in ds if not is_holiday(data, x)]
    hd = [x for x in ds if is_holiday(data, x)]
    wd_amt = sum(t["amount"] for t in exp if not is_holiday(data, d(t["date"])))
    hd_amt = total_exp - wd_amt
    planned_amt = sum(t["amount"] for t in exp if t["planned"])

    var_budget = sum(r[2] for r in var_rows if r[0] == "변동지출")
    big_th = max(30000, int(var_budget * 0.10))
    groups = {}
    for t in exp:
        if t["amount"] < 10000:
            g = groups.setdefault((t["category"], t["sub"]), [0, 0])
            g[0] += 1
            g[1] += t["amount"]
    small = [(c, s, n, amt) for (c, s), (n, amt) in groups.items() if n >= 3]
    small.sort(key=lambda x: -x[3])
    big = [t for t in exp if t["amount"] >= big_th and t["category"] != "고정지출"]

    judged = {j: [] for j in JUDGE}
    for t in exp:
        judged[judge_of(t)].append(t)

    spent_days = {t["date"] for t in exp}
    no_spend = [x for x in ds if x.isoformat() not in spent_days]

    daily, bal = [], start
    min_bal, min_day = start, a
    for x in ds:
        dt = [t for t in txs if t["date"] == x.isoformat()]
        i = sum(t["amount"] for t in dt if t["kind"] == "수입")
        e = sum(t["amount"] for t in dt if t["kind"] == "지출")
        s = sum(t["amount"] for t in dt if t["kind"] == "저축")
        bal += i - e - s
        daily.append({"date": x, "in": i, "exp": e, "sav": s, "bal": bal, "count": len(dt),
                      "holiday": is_holiday(data, x)})
        if bal < min_bal:
            min_bal, min_day = bal, x

    book_end = start + income_tx - total_exp - sav_tx
    act_end = data["settle"].get(key, {}).get("actual_end")
    act_end = parse_amount(act_end) if act_end not in (None, "") else None

    return {
        "key": key, "title": period_title(data, key), "range": (a, b), "txs": txs, "rows": var_rows,
        "inflow_b": inflow_b, "inflow_a": inflow_a, "out_b": out_b, "out_a": out_a,
        "net_b": inflow_b - out_b, "net_a": inflow_a - out_a,
        "spend_b": spend_b, "spend_a": spend_a, "reserve_b": reserve_b, "reserve_used": reserve_used,
        "income": income_tx, "expense": total_exp, "saving": sav_tx, "count": len(exp),
        "cats": cats, "weekday": {"days": len(wd), "amount": wd_amt},
        "holiday": {"days": len(hd), "amount": hd_amt},
        "planned": planned_amt, "unplanned": total_exp - planned_amt,
        "small": small, "big": big, "big_th": big_th, "judged": judged, "no_spend": no_spend,
        "daily": daily, "min_bal": min_bal, "min_day": min_day,
        "start": start, "book_end": book_end, "actual_end": act_end,
    }


def auto_remark(an, grp, name):
    """결산표 비고 자동 문구 — 기록 데이터에서만 산출."""
    if grp == "변동지출":
        ts = [t for t in an["txs"] if t["kind"] == "지출" and t["category"] == name]
        if not ts:
            return "기록 없음"
        up = [t for t in ts if not t["planned"]]
        subs = {}
        for t in ts:
            subs[t["sub"]] = subs.get(t["sub"], 0) + t["amount"]
        top = max(subs, key=subs.get)
        s = f"{len(ts)}건, 주요 {top} {won(subs[top])}"
        if up:
            s += f", 비계획 {len(up)}건 {won(sum(t['amount'] for t in up))}"
        return s
    return ""


def remark(data, an, grp, name):
    r = data["settle"].get(an["key"], {}).get("remarks", {}).get(f"{grp}|{name}")
    return r if r else auto_remark(an, grp, name)


def balance_sheet(data):
    sav_add = sum(t["amount"] for t in data["transactions"] if t["kind"] == "저축")
    m = analyze(data, "month")
    out = []
    for x in data["assets"]:
        s = parse_amount(x.get("start"))
        e = x.get("end")
        out.append({"name": x.get("name", ""), "type": x.get("type", ""), "start": s,
                    "end": parse_amount(e) if e not in (None, "") else None})
    liquid_book = m["book_end"] + sum(o["start"] for o in out if o["type"] == "부채")
    return {"items": out, "savings_added": sav_add, "liquid_book_end": liquid_book}


def goal_drafts(data):
    """상반기 결산에서 예산 초과·비계획 비중이 큰 항목으로 절약 목표 초안 생성."""
    an = analyze(data, "p1")
    p2 = {r[1]: r[4] for r in budget_rows(data) if r[0] == "변동지출"}
    weeks = max(len(an["daily"]) / 7, 1)
    out = []
    cands = []
    for grp, name, bud, act in an["rows"]:
        if grp != "변동지출" or act == 0:
            continue
        ts = [t for t in an["txs"] if t["kind"] == "지출" and t["category"] == name]
        unpl = sum(t["amount"] for t in ts if not t["planned"])
        cands.append((max(act - bud, 0) + unpl * 0.5, name, bud, act, ts, unpl))
    cands.sort(reverse=True)
    for score, name, bud, act, ts, unpl in cands[:3]:
        if score <= 0:
            continue
        subs = {}
        for t in ts:
            subs.setdefault(t["sub"], []).append(t)
        top = max(subs, key=lambda s: sum(t["amount"] for t in subs[s]))
        per_week = len(subs[top]) / weeks
        tgt_week = max(int(per_week * 0.6), 1)
        target = min(p2.get(name, bud), int(act * 0.8 // 1000 * 1000))
        out.append({
            "problem": f"{name} {an['title']} {won(act)}원 사용(예산 {won(bud)}원, 차이 {act - bud:+,}원), "
                       f"비계획 {won(unpl)}원",
            "target": f"후반기 {name} {won(target)}원 이하 사용",
            "action": f"{top} 이용 주 {tgt_week}회 이내(상반기 주 {per_week:.1f}회)",
            "saving": f"{won(max(act - target, 0))}원",
            "check": f"매주 일요일 프로그램 결산 화면에서 {name} 누적액·건수 확인",
            "use": "",
        })
    return out
