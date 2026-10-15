"""보고서 일괄 생성: Excel·Word → PDF → 최종 병합."""
import tempfile
from pathlib import Path

from . import convert, core, export_docx, export_xlsx


def missing(data):
    pr, ev = data["profile"], data["evaluation"]
    out = []
    for k, n in (("name", "성명"), ("student_id", "학번"), ("life_type", "생활 형태"),
                 ("income_sources", "주요 소득"), ("managed", "관리 대상")):
        if not str(pr.get(k, "")).strip():
            out.append(f"기본 정보 · {n}")
    if not data["assets"]:
        out.append("기본 정보 · 재무상태(기초 잔액)")
    if not data["budget"].get("choice"):
        out.append("예산 · 예산안 선택")
    for k in ("p1", "p2"):
        if not core.txs_in(data, k):
            out.append(f"기록 · {core.period_title(data, k)} 기록 없음")
    if data["settle"]["month"].get("actual_end") in (None, ""):
        out.append("결산 · 월말 실제 잔액")
    if not ev.get("goals"):
        out.append("평가 · 절약 목표")
    if not ev.get("feelings", "").strip():
        out.append("평가 · 느낀 점")
    if not any((p.get("principle") or "").strip() for p in ev.get("principles", [])):
        out.append("평가 · 관리 원칙")
    return out


def generate(data, out_dir, log=print):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    a = core.periods(data)["month"][0]
    name = data["profile"].get("name") or "보고서"
    base = f"{a.year}{a.month:02d}_현금흐름보고서_{name}"
    xlsx, docx = out / f"{base}_부속명세서.xlsx", out / f"{base}.docx"
    log("Excel 부속명세서 작성")
    export_xlsx.build(data, xlsx)
    log("Word 보고서 작성")
    export_docx.build(data, docx)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        p1, p2 = td / "report.pdf", td / "annex.pdf"
        import shutil
        shutil.copy(docx, td / "report.docx")
        shutil.copy(xlsx, td / "annex.xlsx")
        log("Word → PDF 변환 (" + convert.to_pdf(td / "report.docx", p1) + ")")
        log("Excel → PDF 변환 (" + convert.to_pdf(td / "annex.xlsx", p2) + ")")
        pdf = out / f"{base}.pdf"
        convert.merge([p1, p2], pdf)
    log(f"완료: {pdf}")
    return {"xlsx": xlsx, "docx": docx, "pdf": pdf}
