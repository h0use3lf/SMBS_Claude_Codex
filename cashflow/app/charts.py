"""보고서용 차트(PNG)."""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from . import core

_names = {f.name for f in font_manager.fontManager.ttflist}
for _n in ("Malgun Gothic", "AppleGothic", "Noto Sans CJK KR", "NanumGothic", "Noto Sans KR"):
    if _n in _names:
        plt.rcParams["font.family"] = _n
        break
plt.rcParams["axes.unicode_minus"] = False
DARK, MID, LIGHT, RED = "#1F2937", "#6B7280", "#D1D5DB", "#B91C1C"


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def budget_vs_actual(an):
    rows = [r for r in an["rows"] if r[0] == "변동지출"]
    names = [r[1] for r in rows][::-1]
    b = [r[2] for r in rows][::-1]
    a = [r[3] for r in rows][::-1]
    fig, ax = plt.subplots(figsize=(6.4, 0.42 * len(names) + 0.8))
    y = range(len(names))
    ax.barh([i + 0.2 for i in y], b, height=0.38, color=LIGHT, label="예산")
    ax.barh([i - 0.2 for i in y], a, height=0.38,
            color=[RED if x > yb else DARK for x, yb in zip(a, b)], label="실적")
    ax.set_yticks(list(y), names, fontsize=8)
    ax.tick_params(axis="x", labelsize=7)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    ax.set_title(f"{an['title']} 변동지출 예산 대비 실적 (원, 적색 = 초과)", fontsize=9, loc="left")
    return _png(fig)


def daily_balance(an):
    xs = [x["date"] for x in an["daily"]]
    ys = [x["bal"] for x in an["daily"]]
    ex = [x["exp"] for x in an["daily"]]
    fig, ax = plt.subplots(figsize=(6.4, 2.4))
    ax.bar(xs, ex, color=LIGHT, label="일 소비지출")
    ax.plot(xs, ys, color=DARK, lw=1.4, marker="o", ms=2.5, label="일말 잔액")
    ax.axhline(0, color=MID, lw=0.6)
    ax.annotate(f"최저 {core.won(an['min_bal'])}", (an["min_day"], an["min_bal"]),
                textcoords="offset points", xytext=(0, -12), fontsize=7, ha="center", color=RED)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%m/%d"))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.tick_params(labelsize=7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=7, frameon=False, loc="upper right")
    ax.set_title(f"{an['title']} 일별 잔액 추이 (원)", fontsize=9, loc="left")
    return _png(fig)
