"""M5: ingestion — section extraction (text), PyMuPDF round-trip."""

from __future__ import annotations

from pathlib import Path

from scidraw_agent.ingest import extract_aims, extract_methods, ingest, read_file

FIX = Path(__file__).parent / "fixtures"


def test_extract_methods_section():
    text = (FIX / "lesion_methods.txt").read_text()
    methods = extract_methods(text)
    assert methods is not None
    assert "lesion mask" in methods.lower()
    assert "introduction" not in methods.lower()  # heading before Methods excluded
    assert "shared nodes converged" not in methods.lower()  # Results excluded


def test_extract_aims_section():
    text = (FIX / "tsc_aim.txt").read_text()
    aims = extract_aims(text)
    assert aims is not None
    assert "aim 1" in aims.lower() and "aim 2" in aims.lower()
    assert "recruit participants" not in aims.lower()  # Research Strategy excluded


def test_ingest_falls_back_to_full_text_when_no_heading():
    raw = "just some pasted prose with no headings about M1 and spinal cord"
    assert ingest(raw, section="methods") == raw


def test_ingest_reads_pdf_methods(tmp_path):
    try:
        import pymupdf as fitz
    except ModuleNotFoundError:  # pragma: no cover
        import fitz

    pdf = tmp_path / "paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Methods")
    page.insert_text((72, 100), "We segmented the lesion mask and normalised to MNI.")
    doc.save(pdf)
    doc.close()

    text = read_file(pdf)
    assert "Methods" in text
    methods = extract_methods(text)
    assert methods and "lesion mask" in methods.lower()
