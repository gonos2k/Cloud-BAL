#!/usr/bin/env python3
"""Build the hourly progress appendix in a new output directory."""
import argparse
import ctypes
import os
import shutil
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
NAME = "HOURLY_PRECIPITATION_PROGRESS_20261030"
SOURCE = HERE / (NAME + ".md")
SCRATCH = None
FIGURES = "evidence/hourly_precipitation_progress_20261030/figures/"


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def format_docx(path):
    doc = Document(path)
    for style in doc.styles:
        if style.type != 1:
            continue
        style.font.name = "NanumMyeongjo"
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.size = Pt(10)
        if style.name == "Title":
            style.font.size = Pt(14)
        elif style.name.startswith("Heading"):
            style.font.size = Pt(11)
        properties = style.element.get_or_add_rPr()
        fonts = properties.rFonts
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            properties.insert(0, fonts)
        for name in ("ascii", "hAnsi", "eastAsia", "cs"):
            fonts.set(qn("w:" + name), "NanumMyeongjo")
    for table in doc.tables:
        widths = [1.4, 3.1, 9.0, 3.5] if len(table.columns) == 4 else [1.5, 1.8, 2.3, 3.5, 4.0, 3.9]
        table.autofit = False
        for column, width in zip(table.columns, widths):
            column.width = Cm(width)
        for row in table.rows:
            for cell, width in zip(row.cells, widths):
                cell.width = Cm(width)
                if len(table.columns) == 6:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(8)
    for paragraph in doc.paragraphs:
        if paragraph.text.startswith("2. 비교와 해석"):
            paragraph.paragraph_format.page_break_before = True
    for section in doc.sections:
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.top_margin = section.bottom_margin = Cm(2)
        section.left_margin = section.right_margin = Cm(2)
    doc.save(path)


def publish_no_replace(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = libc.renameat2
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path, help="new report directory")
    output = parser.parse_args().output_dir.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    source = SOURCE.read_text(encoding="utf-8")
    figures = [HERE / path for path in re.findall(r"!\[[^]]*\]\(([^)]+)\)", source)]
    if len(figures) != 8 or len(set(figures)) != 8:
        raise ValueError("exactly two diagrams and six distinct maps are required")
    inputs = {str(path.relative_to(HERE)): digest(path) for path in [SOURCE, *figures]}
    output.parent.mkdir(parents=True, exist_ok=True)
    global SCRATCH
    scratch = SCRATCH = Path(tempfile.mkdtemp(prefix=".hourly-report-", dir=output.parent))
    docx, pdf = scratch / (NAME + ".docx"), scratch / (NAME + ".pdf")
    result = run("pandoc", "--from=markdown", "--to=docx", "--resource-path=" + str(HERE),
                 str(SOURCE), "--output", str(docx))
    if result.stderr.strip():
        raise RuntimeError("Pandoc warning: " + result.stderr)
    format_docx(docx)
    with ZipFile(docx) as archive:
        images = [name for name in archive.namelist() if name.startswith("word/media/")]
    if len(images) != 8:
        raise RuntimeError(f"expected eight embedded figures; found {len(images)}")
    with tempfile.TemporaryDirectory(prefix="hourly-progress-lo-") as profile:
        run("libreoffice", "-env:UserInstallation=" + Path(profile).as_uri(),
            "--headless", "--convert-to", "pdf", "--outdir", str(scratch), str(docx))
    pdf_text = run("pdftotext", str(pdf), "-").stdout
    if any(token not in pdf_text for token in ("레이더", "CURRENT_OFF", "그림 8")):
        raise RuntimeError("PDF text check failed")
    info = run("pdfinfo", str(pdf)).stdout
    pages = next(int(line.split(":", 1)[1]) for line in info.splitlines() if line.startswith("Pages:"))
    if any(digest(HERE / path) != value for path, value in inputs.items()):
        raise RuntimeError("source or map changed during conversion")
    # The attachment is located one level below figures and three below docs.
    attachment = re.sub(r"(?<!!)(\]\()([^):]+)(\))", r"\1../../../\2\3", source)
    attachment = attachment.replace("](" + FIGURES, "](../figures/")
    attachment = attachment.replace("](evidence/hourly_precipitation_progress_20261030/concepts/", "](../concepts/")
    (scratch / (NAME + ".md")).write_text(attachment, encoding="utf-8")
    receipt = {"input_sha256": inputs, "docx_sha256": digest(docx), "pdf_sha256": digest(pdf),
               "embedded_figures": len(images), "pdf_pages": pages,
               "pandoc": run("pandoc", "--version").stdout.splitlines()[0],
               "libreoffice": run("libreoffice", "--version").stdout.splitlines()[0],
               "note": "Conversion checks do not replace visual review."}
    (scratch / "build_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    publish_no_replace(scratch, output)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Preserve any failed temporary build outside the tracked tree.
        if SCRATCH is not None and SCRATCH.exists():
            shutil.move(str(SCRATCH), tempfile.mkdtemp(prefix="hourly-report-failed-", dir="/var/tmp"))
        raise
