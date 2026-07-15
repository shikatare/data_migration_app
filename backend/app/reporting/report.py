"""Generates a downloadable PDF conversion-review report from a run record.

Built for a human reviewer: overall confidence, the checks performed, a
per-table and per-column confidence breakdown, the items that need review,
and a sign-off block. Styled in the app's cream/charcoal/gold palette.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

INK = colors.HexColor("#2E2A24")
GOLD = colors.HexColor("#CBB047")
GOLD_SOFT = colors.HexColor("#F1E7C6")
CREAM = colors.HexColor("#FBF8F0")
BORDER = colors.HexColor("#D4C8AB")
MUTED = colors.HexColor("#857E72")
GREEN = colors.HexColor("#5E7A4B")
RUST = colors.HexColor("#B4553E")
OCHRE = colors.HexColor("#9A8748")


def _conf_color(conf):
    if conf is None:
        return MUTED
    if conf >= 0.90:
        return GREEN
    if conf >= 0.70:
        return OCHRE
    return RUST


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1x", parent=ss["Heading1"], textColor=INK, fontSize=20, spaceAfter=2))
    ss.add(ParagraphStyle("Subx", parent=ss["Normal"], textColor=MUTED, fontSize=9.5, spaceAfter=10))
    ss.add(ParagraphStyle("H2x", parent=ss["Heading2"], textColor=INK, fontSize=12,
                          spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("Bodyx", parent=ss["Normal"], textColor=INK, fontSize=9.5, leading=13))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], textColor=MUTED, fontSize=8, leading=11))
    ss.add(ParagraphStyle("Mono", parent=ss["Code"], textColor=INK, fontSize=7.5, leading=10))
    return ss


def _kv_table(rows):
    t = Table(rows, colWidths=[45 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
    ]))
    return t


def build_report(record: dict) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Migration Review — {record.get('schemaName','')}")
    story = []
    vd = record.get("validateDeploy") or {}
    scoring = vd.get("scoring") or {}
    convert = record.get("convert") or {}
    overall = scoring.get("overallConfidence")

    # ---- Header ----
    story.append(Paragraph("MySQL &rarr; Snowflake Migration", ss["H1x"]))
    story.append(Paragraph("Conversion Review Report", ss["Subx"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=10))

    conf_pct = f"{int(overall * 100)}%" if overall is not None else "n/a"
    story.append(_kv_table([
        ["Run ID", record.get("runId", "")],
        ["Source schema", record.get("schemaName", "")],
        ["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
        ["Run status", str(record.get("overallStatus", "")).replace("_", " ")],
        ["Overall confidence", conf_pct],
        ["Recommendation", scoring.get("recommendation", "—")],
    ]))

    # ---- Checks performed ----
    story.append(Paragraph("Validation checks performed", ss["H2x"]))
    syntax_errors = vd.get("syntaxErrors", [])
    diff_issues = vd.get("diffIssues", [])
    rule_violations = vd.get("ruleViolations", [])
    checks = [
        ["Check", "Result"],
        ["1. DDL syntax parse (Snowflake dialect)",
         "PASS" if not syntax_errors else f"FAIL — {len(syntax_errors)} error(s)"],
        ["2. Structural diff (no dropped columns vs source)",
         "PASS" if not diff_issues else f"FAIL — {len(diff_issues)} issue(s)"],
        ["3. Business rules (naming, disallowed types)",
         "PASS" if not rule_violations else f"{len(rule_violations)} warning(s)"],
    ]
    ct = Table(checks, colWidths=[120 * mm, 45 * mm])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), CREAM),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (0, -1), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [CREAM, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ct)

    # ---- Per-table confidence ----
    story.append(Paragraph("Per-table confidence", ss["H2x"]))
    rows = [["Table", "Cols", "Confidence", "Level"]]
    for t in scoring.get("tables", []):
        rows.append([t["table"], str(t["columnCount"]),
                     f"{int(t['confidence']*100)}%", t["level"]])
    tt = Table(rows, colWidths=[70 * mm, 20 * mm, 40 * mm, 35 * mm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), CREAM),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, t in enumerate(scoring.get("tables", []), start=1):
        style.append(("TEXTCOLOR", (2, i), (2, i), _conf_color(t["confidence"])))
    tt.setStyle(TableStyle(style))
    story.append(tt)

    # ---- Items requiring review ----
    review_items = scoring.get("reviewItems", [])
    story.append(Paragraph(f"Items for human review ({len(review_items)})", ss["H2x"]))
    if not review_items:
        story.append(Paragraph("None — all conversions scored high confidence.", ss["Bodyx"]))
    else:
        rrows = [["Table.Column", "Mapping", "Conf.", "Reviewer note"]]
        for r in review_items:
            rrows.append([
                Paragraph(f"<b>{r['table']}</b>.{r['column']}", ss["Small"]),
                Paragraph(f"{r['sourceType']} &rarr; {r['snowflakeType']}", ss["Small"]),
                Paragraph(f"{int(r['confidence']*100)}%", ss["Small"]),
                Paragraph(r["note"], ss["Small"]),
            ])
        rt = Table(rrows, colWidths=[38 * mm, 34 * mm, 15 * mm, 78 * mm])
        rstyle = [
            ("BACKGROUND", (0, 0), (-1, 0), GOLD_SOFT),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, r in enumerate(review_items, start=1):
            rstyle.append(("TEXTCOLOR", (2, i), (2, i), _conf_color(r["confidence"])))
        rt.setStyle(TableStyle(rstyle))
        story.append(rt)

    # ---- Warnings & unmapped ----
    warnings = convert.get("warnings", [])
    unmapped = convert.get("unmappedTypes", [])
    if warnings or unmapped:
        story.append(Paragraph("Conversion warnings & unmapped types", ss["H2x"]))
        for w in warnings:
            story.append(Paragraph(f"&bull; <b>{w.get('table','')}</b>: {w.get('message','')}", ss["Small"]))
        for u in unmapped:
            story.append(Paragraph(
                f"&bull; <b>{u.get('table','')}.{u.get('column','')}</b> — unmapped source type "
                f"{u.get('sourceType','')}", ss["Small"]))

    # ---- Converted DDL appendix ----
    story.append(Paragraph("Appendix — converted Snowflake DDL", ss["H2x"]))
    for t in convert.get("convertedTables", []):
        ddl = (t.get("ddl") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(ddl, ss["Mono"]))
        story.append(Spacer(1, 4))

    # ---- Sign-off ----
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER, spaceAfter=8))
    story.append(Paragraph("Reviewer sign-off", ss["H2x"]))
    signoff = Table([
        ["Reviewed by", "________________________", "Date", "____________"],
        ["Decision", "\u2610 Approve    \u2610 Approve with changes    \u2610 Reject", "", ""],
    ], colWidths=[28 * mm, 80 * mm, 18 * mm, 40 * mm])
    signoff.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("SPAN", (1, 1), (3, 1)),
    ]))
    story.append(signoff)

    doc.build(story)
    return buf.getvalue()