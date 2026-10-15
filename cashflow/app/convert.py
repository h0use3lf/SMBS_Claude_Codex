"""Word·Excel → PDF 변환 및 병합 (MS Office 우선, LibreOffice 대체)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pypdf import PdfWriter


def _soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(p):
            return p
    return None


def _office(src, dst):
    import win32com.client  # pywin32
    src, dst = str(Path(src).resolve()), str(Path(dst).resolve())
    if src.lower().endswith(".docx"):
        app = win32com.client.DispatchEx("Word.Application")
        app.Visible = False
        try:
            doc = app.Documents.Open(src, ReadOnly=True)
            doc.Fields.Update()
            doc.ExportAsFixedFormat(dst, 17)
            doc.Close(False)
        finally:
            app.Quit()
    else:
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        try:
            wb = app.Workbooks.Open(src, ReadOnly=True)
            wb.ExportAsFixedFormat(0, dst)
            wb.Close(False)
        finally:
            app.Quit()


def _libre(src, dst):
    exe = _soffice()
    if not exe:
        raise RuntimeError("PDF 변환 프로그램을 찾지 못했습니다. MS Office 또는 LibreOffice를 설치하세요.")
    out = Path(dst).parent
    flags = 0x08000000 if sys.platform == "win32" else 0
    subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", str(out), str(src)],
                   check=True, capture_output=True, timeout=180, creationflags=flags)
    made = out / (Path(src).stem + ".pdf")
    if made.resolve() != Path(dst).resolve():
        made.replace(dst)


def to_pdf(src, dst):
    errors = []
    if sys.platform == "win32":
        try:
            _office(src, dst)
            return "MS Office"
        except Exception as e:
            errors.append(f"MS Office: {e}")
    try:
        _libre(src, dst)
        return "LibreOffice"
    except Exception as e:
        errors.append(f"LibreOffice: {e}")
    raise RuntimeError("\n".join(errors))


def merge(parts, dst):
    w = PdfWriter()
    for p in parts:
        w.append(str(p))
    with open(dst, "wb") as f:
        w.write(f)
    return dst
