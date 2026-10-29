#!/usr/bin/env python3
"""Build a Korean A4 DOCX and PDF from the conference-paper Markdown."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "CURRENT_FORECAST_CONFERENCE_PAPER_20261029.md"
NAME = "CURRENT_FORECAST_CONFERENCE_PAPER_20261029"


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_font(style):
    style.font.name = "NanumMyeongjo"
    style.font.size = Pt(10)
    properties = style.element.get_or_add_rPr()
    fonts = properties.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        properties.insert(0, fonts)
    for name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + name), "NanumMyeongjo")


def format_docx(path):
    doc = Document(path)
    for style in doc.styles:
        if style.type == 1:
            set_font(style)
    for section in doc.sections:
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.top_margin = section.bottom_margin = Cm(2.2)
        section.left_margin = section.right_margin = Cm(2.2)
    doc.save(path)


def check_docx(path):
    with ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
              "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        maths = root.xpath("//m:oMath", namespaces=ns)
        text = "".join(root.xpath("//w:t/text()|//m:t/text()", namespaces=ns))
        if not maths or any(token in text for token in (r"\frac", r"\tag", r"\mathrm")):
            raise RuntimeError("DOCX equation conversion failed")
        return len(maths), len([x for x in archive.namelist() if x.startswith("word/media/")])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path, help="new output directory")
    parser.add_argument("--require-figures", action="store_true", help="require figures in the final document")
    args = parser.parse_args()
    if args.output_dir.is_symlink():
        raise ValueError("output directory must not be a symlink")
    output = args.output_dir.resolve()
    markdown = SOURCE.read_text()
    figures = [HERE / path for path in re.findall(r"!\[[^]]*\]\(([^)]+)\)", markdown)]
    if args.require_figures and not figures:
        raise ValueError("final paper has no embedded figure references")
    inputs = {str(path.resolve()): sha256(path) for path in [SOURCE, *figures]}
    output.mkdir(parents=True, exist_ok=False)
    docx = output / (NAME + ".docx")
    pdf = output / (NAME + ".pdf")
    try:
        result = run("pandoc", "--from=markdown+tex_math_single_backslash", "--to=docx",
                     "--resource-path=" + str(HERE), str(SOURCE), "--output", str(docx))
        if result.stderr.strip():
            raise RuntimeError("Pandoc warning: " + result.stderr)
        format_docx(docx)
        maths, images = check_docx(docx)
        if images < len(set(figures)):
            raise RuntimeError("not all referenced figures were embedded in DOCX")
        with tempfile.TemporaryDirectory(prefix="cloudbal-lo-profile-") as profile:
            run("libreoffice", "-env:UserInstallation=" + Path(profile).as_uri(),
                "--headless", "--convert-to", "pdf", "--outdir", str(output), str(docx))
        info = run("pdfinfo", str(pdf)).stdout
        pages = next(int(line.split(":", 1)[1]) for line in info.splitlines()
                     if line.startswith("Pages:"))
        extracted = run("pdftotext", str(pdf), "-").stdout
        if "국문 초록" not in extracted or any(x in extracted for x in (r"\frac", r"\tag", r"\mathrm")):
            raise RuntimeError("PDF text or math conversion failed")
        if any(sha256(Path(path)) != digest for path, digest in inputs.items()):
            raise RuntimeError("paper source or figure changed during conversion")
        metadata = {
            "input_sha256": inputs, "source_sha256": inputs[str(SOURCE.resolve())], "docx_sha256": sha256(docx),
            "pdf_sha256": sha256(pdf), "docx_math_objects": maths,
            "docx_embedded_images": images, "pdf_pages": pages,
            "pandoc": run("pandoc", "--version").stdout.splitlines()[0],
            "libreoffice": run("libreoffice", "--version").stdout.splitlines()[0],
            "pdfinfo": run("pdfinfo", "-v").stderr.splitlines()[0],
            "font": "NanumMyeongjo", "paper": "A4",
            "note": "Automated conversion checks do not replace visual review."
        }
        (output / "build_receipt.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
    except Exception:
        # Leave failed outputs for inspection; never overwrite an existing directory.
        raise


if __name__ == "__main__":
    main()
