import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymupdf

from pdf_toolbox.core.ops import (
    annotate, compress, convert, crop, extract, pages, redact, security, stamp,
)

FX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test-fixtures"))
TMP = tempfile.mkdtemp(prefix="pdftest_")
print("TMP:", TMP)

def p(*a):
    print("  ", *a)

# ---- extract text
txt = extract.extract_text(os.path.join(FX, "extract-text-test.pdf"), fmt="txt")
p("txt len", len(txt), "| head:", txt[:60].replace("\n", " "))
md = extract.extract_text(os.path.join(FX, "extract-text-test.pdf"), fmt="markdown")
p("md len", len(md))
js = extract.extract_text(os.path.join(FX, "extract-text-test.pdf"), fmt="json")
p("json len", len(js), "valid:", js.strip().startswith("{"))
pages_txt = extract.extract_text_pages(os.path.join(FX, "extract-text-test.pdf"))
p("pages:", [(x.index, x.char_count, x.word_count) for x in pages_txt])

# ---- extract images
imgs = extract.list_images(os.path.join(FX, "images-test.pdf"))
p("images found:", [(i.page, i.width, i.height, i.has_alpha) for i in imgs])
res = extract.extract_images(os.path.join(FX, "images-test.pdf"), os.path.join(TMP, "imgs"))
p("extracted:", [(os.path.basename(r.filename), r.ext, r.size_bytes) for r in res])
zp = extract.extract_images_zip(os.path.join(FX, "images-test.pdf"), os.path.join(TMP, "imgs.zip"))
p("zip size", os.path.getsize(os.path.join(TMP, "imgs.zip")))

# ---- metadata
meta = extract.read_metadata(os.path.join(FX, "extract-text-test.pdf"))
p("meta:", meta.non_empty_standard(), "fonts:", meta.fonts[:2], "imgs:", meta.image_count)
d = pymupdf.open(os.path.join(FX, "extract-text-test.pdf"))
removed = extract.clean_metadata(d, extract.CleanOptions())
p("cleaned keys:", list(removed.get("metadata", {}).keys()), "after:", {k: v for k, v in d.metadata.items() if v})
d.close()

# ---- security
enc = os.path.join(TMP, "enc.pdf")
security.encrypt_file(
    os.path.join(FX, "extract-text-test.pdf"), enc,
    security.EncryptOptions(user_password="abc123", owner_password="own", algorithm=security.ALGO_AES256),
)
info = security.probe_encryption(enc, "abc123")
p("encrypted:", info["encrypted"], "needs:", info["needs_password"], "method:", info["method"])
p("perms:", {k: v for k, v in info["permission_detail"].items() if v})
p("verify pw:", security.verify_password(enc, "abc123"), security.verify_password(enc, "wrong"))
enc2 = os.path.join(TMP, "enc2.pdf")
security.encrypt_file(
    os.path.join(FX, "extract-text-test.pdf"), enc2,
    security.EncryptOptions(user_password="u", owner_password="o",
                            permission_keys=["print", "accessibility"]),
)
p("restricted perms:", {k: v for k, v in security.probe_encryption(enc2, "u")["permission_detail"].items()})
dec = os.path.join(TMP, "dec.pdf")
security.decrypt_file(enc, dec, "abc123")
p("decrypted needs_pass:", security.probe_encryption(dec)["needs_password"])

# ---- compress
for level in [compress.LEVEL_LOSSLESS, compress.LEVEL_BALANCED, compress.LEVEL_STRONG, compress.LEVEL_EXTREME]:
    out = os.path.join(TMP, f"c_{level}.pdf")
    r = compress.compress_file(os.path.join(FX, "images-test.pdf"), out, compress.CompressOptions(level=level))
    p(f"compress {level}: {r.before} -> {r.after} ({r.ratio:.2%})")

# ---- redact
d = pymupdf.open(os.path.join(FX, "extract-text-test.pdf"))
matches = redact.find_matches(d, range(d.page_count), pattern_keys=["email"], keywords=["test"])
p("redact matches:", [(m.page, m.kind, m.text) for m in matches][:6], "total", len(matches))
n = redact.add_redactions(d, matches)
p("annots added:", n)
rep = redact.apply_redactions(d)
p("applied:", rep.applied, "pages:", rep.pages_touched)
p("text gone:", "test document" not in d.load_page(0).get_text())
d.close()

# ---- stamp watermark
d = pymupdf.open(os.path.join(FX, "extract-text-test.pdf"))
n = stamp.apply_watermark(d, stamp.WatermarkSettings(text="机密 CONFIDENTIAL", font_size=40, opacity=0.3, rotation=-45, mode="tiled", tile_spacing_x=150, tile_spacing_y=150))
p("watermark pages:", n, "| text present:", "机密" in d.load_page(0).get_text())
rep = stamp.apply_page_numbers(d, stamp.PageNumberSettings(fmt=stamp.FMT_ZH_OF, position="bottom-center", header_left="Qudo", footer_right="{filename}"))
p("page numbers:", rep)
p("page1 has 第 1 页:", "第 1 页" in d.load_page(0).get_text())
d.close()

# ---- fill & sign
d = pymupdf.open(os.path.join(FX, "extract-text-test.pdf"))
sig = stamp.render_signature_image([[(10, 40), (30, 10), (60, 35), (90, 8)], [(20, 50), (80, 50)]], 120, 60, pen_width=3)
p("sig png bytes:", len(sig))
els = [
    stamp.FillElement(kind=stamp.KIND_TEXT, page=0, x=72, y=700, width=200, height=16, text="签署人：张三", font_size=12),
    stamp.FillElement(kind=stamp.KIND_DATE, page=0, x=300, y=700, width=120, height=16, text=stamp.format_date(None, "YYYY-MM-DD")),
    stamp.FillElement(kind=stamp.KIND_CHECK, page=0, x=72, y=660, width=16, height=16, font_size=14),
    stamp.FillElement(kind=stamp.KIND_DRAWN_SIG, page=0, x=72, y=600, width=120, height=60, image_bytes=sig),
]
p("fill drawn:", stamp.apply_fill_elements(d, els))
p("page has 张三:", "张三" in d.load_page(0).get_text())
fi = stamp.detect_form_info(d)
p("form info:", fi["has_form_fields"], fi["has_digital_signature"])
d.close()

# ---- annotate
d = pymupdf.open(os.path.join(FX, "extract-text-test.pdf"))
pg = d.load_page(0)
words = pg.get_text("words")
r0 = pymupdf.Rect(*words[0][:4]) if words else pymupdf.Rect(70, 70, 200, 85)
specs = [
    annotate.AnnotationSpec(type=annotate.T_HIGHLIGHT, page=0, rect=tuple(r0), color="#FFFF00", opacity=0.4),
    annotate.AnnotationSpec(type=annotate.T_TEXT, page=0, rect=(70, 120, 300, 145), text="中文批注", color="#FF0000", font_size=12),
    annotate.AnnotationSpec(type=annotate.T_NOTE, page=0, rect=(400, 100, 424, 124), note_content="这里要改", note_author="Jee"),
    annotate.AnnotationSpec(type=annotate.T_RECT, page=0, rect=(70, 200, 300, 260), color="#0000FF", line_width=2),
    annotate.AnnotationSpec(type=annotate.T_CIRCLE, page=0, rect=(320, 200, 420, 260), color="#00AA00"),
    annotate.AnnotationSpec(type=annotate.T_ARROW, page=0, p1=(70, 300), p2=(200, 330), color="#FF0000", line_width=2),
    annotate.AnnotationSpec(type=annotate.T_FREEHAND, page=0, points=[[(70, 400), (100, 420), (140, 395), (180, 415)]], color="#FF0000", line_width=2),
    annotate.AnnotationSpec(type=annotate.T_STAMP, page=0, rect=(70, 450, 200, 490), stamp_text="APPROVED"),
    annotate.AnnotationSpec(type=annotate.T_UNDERLINE, page=0, rect=tuple(r0), color="#0000FF"),
    annotate.AnnotationSpec(type=annotate.T_STRIKEOUT, page=0, rect=tuple(r0), color="#FF0000"),
]
for s in specs:
    annotate.add_annotation(d, s)
lst = annotate.list_annotations(d)
p("annots:", [(a["page"], a["type_label"], annotate.annotation_summary(a)) for a in lst])
p("delete:", annotate.delete_annotation(d, 0, lst[-1]["xref"]), "now", len(annotate.list_annotations(d)))
d2 = pymupdf.open(stream=d.tobytes(), filetype="pdf")
annotate.flatten_annotations(d2)
p("flattened annots left:", len(annotate.list_annotations(d2)))
d2.close()
d.close()

# ---- convert word
for mode in [convert.WORD_EDITABLE, convert.WORD_TEXT, convert.WORD_FIDELITY]:
    out = os.path.join(TMP, f"w_{mode}.docx")
    convert.pdf_to_word(os.path.join(FX, "extract-text-test.pdf"), out, mode=mode)
    p(f"word {mode}:", os.path.getsize(out))

# ---- convert excel
tabs = convert.detect_tables(os.path.join(FX, "..", "test-table.pdf"))
p("tables:", [(t.page, t.index, t.row_count, t.col_count, t.method) for t in tabs])
out = os.path.join(TMP, "t.xlsx")
convert.export_tables(tabs, out, fmt=convert.EXCEL_XLSX, sheet_mode=convert.SHEET_PER_TABLE)
p("xlsx:", os.path.getsize(out))
out = os.path.join(TMP, "t.csv")
convert.export_tables(tabs, out, fmt=convert.EXCEL_CSV)
p("csv:", os.path.getsize(out))
out = os.path.join(TMP, "t_single.xlsx")
convert.export_tables(tabs, out, sheet_mode=convert.SHEET_SINGLE)
p("xlsx single:", os.path.getsize(out))

print("\nALL ENGINE TESTS DONE")
