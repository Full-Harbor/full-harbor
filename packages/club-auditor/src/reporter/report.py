"""
Club Auditor — Combined Report Card Generator
=============================================
Combines the 20-question parent experience audit + GEO/AIO score
into a single formatted report card (text or HTML).

Features:
- Login wall / member-only content detection
- Top 3 improvement recommendations ranked by parent impact
- Text and HTML output formats
- Self-contained HTML report card

Usage:
  python report.py --url https://... --club-name "Lakewood YC" --format text
  python report.py --url https://... --club-name "Houston YC" --format html --out /tmp/report.html
"""

from __future__ import annotations

import argparse
import html as html_lib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Allow running as a standalone script from any working directory
sys.path.insert(0, str(Path(__file__).parents[1]))

from analyzer.audit import audit_page, scrape_text, PageAudit, Score
from analyzer.geo_scorer import score_url, GEOReport


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGIN_WALL_THRESHOLD = 500  # chars of visible text; below this = login wall

PLATFORM_RISK_TEXT = (
    "PLATFORM VISIBILITY RISK \u2014 content may be hidden behind authentication. "
    "This page is invisible to Google AND to AI systems."
)

PLATFORM_RISK_FLAG = f"\u26a0\ufe0f  {PLATFORM_RISK_TEXT}"

# Short display labels for the 20 parent questions
QUESTION_LABELS: dict[int, str] = {
    1: "Experience level",
    2: "Ages",
    3: "Non-member",
    4: "Price",
    5: "Scholarship",
    6: "Dates",
    7: "Typical day",
    8: "Swim req.",
    9: "What to bring",
    10: "Certified",
    11: "Coaches named",
    12: "Ratio",
    13: "Boat types",
    14: "Safety info",
    15: "Weather policy",
    16: "Parent viewing",
    17: "Trial option",
    18: "Registration",
    19: "Cancellation",
    20: "Year-round",
}

# (priority 10=highest, recommendation text) for missing questions
QUESTION_IMPROVEMENTS: dict[int, tuple[int, str]] = {
    4:  (10, "Publish clear pricing for members and non-members"),
    1:  (9,  'Publish "No experience required" on every program page'),
    2:  (8,  "State age/grade eligibility prominently on program pages"),
    10: (7,  "Name coaches with US Sailing certification status"),
    6:  (7,  "Publish specific program dates and weekly schedule"),
    12: (6,  "Add coach-to-student ratio to build parent confidence"),
    8:  (6,  "Clearly state swim requirement and life-jacket policy"),
    18: (5,  "Make the registration link prominent with a direct call-to-action"),
    5:  (5,  "Mention scholarship or financial assistance availability"),
    11: (4,  "Add a staff/coach page with names and bios"),
    3:  (4,  "Explicitly state whether membership is required"),
    7:  (3,  "Describe a typical camp day with a sample schedule"),
    9:  (3,  'Add a "What to bring" packing list'),
    14: (3,  "Add a safety section describing PFDs and protocols"),
    15: (2,  "Explain the weather cancellation policy"),
    13: (2,  "Name the boats used (Opti, 420, Laser, etc.)"),
    16: (1,  "Let parents know whether they can watch sessions"),
    17: (1,  "Offer a trial class or introductory session option"),
    19: (1,  "Publish the refund and cancellation policy"),
    20: (1,  "Mention year-round or fall/spring programs if available"),
}

# (priority, keyword_in_gap_text, recommendation) for GEO gaps
GEO_GAP_IMPROVEMENTS: list[tuple[int, str, str]] = [
    (8,  "No pricing",       "Add clear pricing \u2014 it\u2019s the #1 parent question and a top GEO signal"),
    (7,  "meta description", "Add a meta description summarizing the program for AI and Google"),
    (7,  "FAQ",              "Add FAQ-style Q&A headers \u2014 AI uses these to generate overviews"),
    (6,  "No age",           "State age eligibility explicitly \u2014 parents and AI both look for this"),
    (6,  "No dates",         "Publish specific dates \u2014 AI treats pages without dates as stale"),
    (5,  "Schema.org",       "Add Schema.org EducationalEvent markup for better AI extraction"),
    (5,  "<h1>",             "Add a descriptive <h1> with the program name and year"),
    (4,  "No contact",       "Add a contact name, email, and phone number to the program page"),
    (3,  "title",            "Improve <title> tag: use \u2018Program Name | Club Name | Year\u2019 format"),
    (3,  "Year",             "Add the current year to keep content fresh for AI systems"),
    (2,  "viewport",         "Add a viewport meta tag to signal mobile-friendliness"),
]

CATEGORY_ORDER = [
    "eligibility", "cost", "logistics", "safety",
    "instruction", "program", "parent_experience", "conversion",
]

CATEGORY_LABELS = {
    "eligibility":       "ELIGIBILITY",
    "cost":              "COST",
    "logistics":         "LOGISTICS",
    "safety":            "SAFETY",
    "instruction":       "INSTRUCTION",
    "program":           "PROGRAM",
    "parent_experience": "PARENT EXP.",
    "conversion":        "CONVERSION",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grade(pct: float) -> str:
    if pct >= 85:
        return "A"
    if pct >= 70:
        return "B"
    if pct >= 55:
        return "C"
    if pct >= 40:
        return "D"
    return "F"


def _audit_date() -> str:
    dt = datetime.now(timezone.utc)
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def _grade_color(g: str) -> str:
    return {
        "A": "#2e7d32",
        "B": "#388e3c",
        "C": "#f9a825",
        "D": "#e65100",
        "F": "#c62828",
    }.get(g, "#333")


# ---------------------------------------------------------------------------
# Login wall detection
# ---------------------------------------------------------------------------

def is_login_wall(url: str) -> bool:
    """Return True if the URL appears to be behind a login wall (< LOGIN_WALL_THRESHOLD chars)."""
    text = scrape_text(url)
    return text is None or len(text.strip()) < LOGIN_WALL_THRESHOLD


# ---------------------------------------------------------------------------
# Recommendation builder
# ---------------------------------------------------------------------------

def build_top_recommendations(
    audit: PageAudit,
    geo: GEOReport,
    top_n: int = 3,
) -> list[str]:
    """Rank improvement recommendations by parent impact and return the top_n."""
    candidates: list[tuple[int, str]] = []

    # From 20-question audit — questions not answered
    for q in audit.questions:
        if q.score == Score.NOT_FOUND and q.question_id in QUESTION_IMPROVEMENTS:
            priority, rec = QUESTION_IMPROVEMENTS[q.question_id]
            candidates.append((priority, rec))

    # From GEO dimension gaps
    geo_gaps_text = " ".join(g for dim in geo.dimensions for g in dim.gaps)
    for priority, keyword, rec in GEO_GAP_IMPROVEMENTS:
        if keyword.lower() in geo_gaps_text.lower():
            if not any(rec == r for _, r in candidates):
                candidates.append((priority, rec))

    # Sort by priority descending; deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for _, rec in sorted(candidates, key=lambda x: -x[0]):
        if rec not in seen:
            seen.add(rec)
            unique.append(rec)

    return unique[:top_n]


# ---------------------------------------------------------------------------
# Text report card
# ---------------------------------------------------------------------------

def format_text(
    club_name: str,
    url: str,
    audit: PageAudit,
    geo: GEOReport,
    login_wall: bool,
    recommendations: list[str],
) -> str:
    s = audit.score_summary
    parent_pct = s["pct_found"]
    parent_grade = _grade(parent_pct)

    lines: list[str] = []
    lines.append("=" * 55)
    lines.append("=== FULL HARBOR PARENT EXPERIENCE REPORT CARD ===")
    lines.append("=" * 55)
    lines.append(f"Club:    {club_name}")
    lines.append(f"URL:     {url}")
    lines.append(f"Audited: {_audit_date()}")
    lines.append("")

    if login_wall:
        lines.append(PLATFORM_RISK_FLAG)
        lines.append("")

    lines.append(
        f"PARENT EXPERIENCE SCORE: {s['found']}/{s['total']} ({parent_pct}%) \u2014 Grade: {parent_grade}"
    )
    lines.append(
        f"GEO/AIO READINESS:        {geo.total_score}/{geo.max_score}      \u2014 Grade: {geo.grade}"
    )
    lines.append("")

    by_category: dict[str, list] = {}
    for q in audit.questions:
        by_category.setdefault(q.category, []).append(q)

    for cat in CATEGORY_ORDER:
        qs = by_category.get(cat, [])
        if not qs:
            continue
        label = CATEGORY_LABELS.get(cat, cat.upper())
        parts = [f"{q.score.value} {QUESTION_LABELS[q.question_id]}" for q in qs]
        lines.append(f"{label:<14} " + "  ".join(parts))

    lines.append("")
    lines.append("TOP 3 IMPROVEMENTS:")
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"{i}. {rec}")

    lines.append("")
    lines.append("=" * 55)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML report card
# ---------------------------------------------------------------------------

def format_html(
    club_name: str,
    url: str,
    audit: PageAudit,
    geo: GEOReport,
    login_wall: bool,
    recommendations: list[str],
) -> str:
    s = audit.score_summary
    parent_pct = s["pct_found"]
    parent_grade = _grade(parent_pct)

    # Build category grid rows
    by_category: dict[str, list] = {}
    for q in audit.questions:
        by_category.setdefault(q.category, []).append(q)

    category_rows_html = ""
    for cat in CATEGORY_ORDER:
        qs = by_category.get(cat, [])
        if not qs:
            continue
        label = CATEGORY_LABELS.get(cat, cat.upper())
        cells = "".join(
            f'<span class="q-cell q-{q.score.name.lower()}" title="{html_lib.escape(q.question)}">'
            f"{q.score.value} {html_lib.escape(QUESTION_LABELS[q.question_id])}"
            f"</span>"
            for q in qs
        )
        category_rows_html += (
            f'<tr><td class="cat-label">{html_lib.escape(label)}</td>'
            f'<td class="cat-cells">{cells}</td></tr>\n'
        )

    # GEO dimension progress bars
    geo_bars_html = ""
    for dim in geo.dimensions:
        pct = round(100 * dim.earned / dim.max_points) if dim.max_points else 0
        geo_bars_html += (
            f'<div class="geo-row">'
            f'<span class="geo-label">{html_lib.escape(dim.name)}</span>'
            f'<div class="geo-bar-wrap">'
            f'<div class="geo-bar" style="width:{pct}%"></div></div>'
            f'<span class="geo-score">{dim.earned}/{dim.max_points}</span>'
            f"</div>\n"
        )

    recs_html = "".join(f"<li>{html_lib.escape(r)}</li>" for r in recommendations)

    login_wall_html = ""
    if login_wall:
        login_wall_html = (
            '<div class="risk-banner">'
            f"\u26a0\ufe0f {html_lib.escape(PLATFORM_RISK_TEXT)}"
            "</div>"
        )

    audited = _audit_date()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Full Harbor Report Card \u2014 {html_lib.escape(club_name)}</title>
<style>
  body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f5f5f5;margin:0;padding:20px;color:#222;}}
  .card {{max-width:760px;margin:0 auto;background:#fff;border-radius:12px;
          box-shadow:0 2px 16px rgba(0,0,0,.12);overflow:hidden;}}
  .header {{background:#0d2a4a;color:#fff;padding:28px 32px 20px;}}
  .header h1 {{margin:0 0 4px;font-size:1.1rem;text-transform:uppercase;
               letter-spacing:.08em;opacity:.7;}}
  .header h2 {{margin:0 0 8px;font-size:1.8rem;}}
  .header .meta {{font-size:.85rem;opacity:.7;}}
  .body {{padding:28px 32px;}}
  .scores {{display:flex;gap:24px;margin-bottom:28px;flex-wrap:wrap;}}
  .score-box {{flex:1;min-width:200px;border:2px solid #e0e0e0;border-radius:10px;
               padding:16px 20px;}}
  .score-box .label {{font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;
                      color:#666;margin-bottom:6px;}}
  .score-box .value {{font-size:2rem;font-weight:700;}}
  .score-box .grade {{display:inline-block;margin-left:8px;font-size:1.4rem;font-weight:700;}}
  .sub {{font-size:.8rem;color:#777;margin-top:4px;}}
  .risk-banner {{background:#fff3cd;border-left:4px solid #ffc107;padding:12px 16px;
                 margin-bottom:20px;border-radius:4px;font-weight:600;font-size:.9rem;}}
  .audit-table {{width:100%;border-collapse:collapse;margin-bottom:28px;}}
  .audit-table td {{padding:6px 4px;vertical-align:top;}}
  .cat-label {{font-weight:700;font-size:.78rem;text-transform:uppercase;
               letter-spacing:.05em;color:#555;white-space:nowrap;width:110px;}}
  .q-cell {{display:inline-block;margin:2px 4px;font-size:.8rem;border-radius:4px;
            padding:2px 6px;}}
  .q-found {{background:#e8f5e9;}}
  .q-partial {{background:#fff8e1;}}
  .q-not_found {{background:#fce4e4;}}
  .section-title {{font-size:.85rem;text-transform:uppercase;letter-spacing:.06em;
                   color:#555;margin:0 0 12px;}}
  .geo-section {{margin-bottom:28px;}}
  .geo-row {{display:flex;align-items:center;gap:10px;margin-bottom:6px;}}
  .geo-label {{width:160px;font-size:.82rem;color:#444;flex-shrink:0;}}
  .geo-bar-wrap {{flex:1;background:#eee;border-radius:4px;height:12px;overflow:hidden;}}
  .geo-bar {{height:100%;background:#1565c0;border-radius:4px;}}
  .geo-score {{width:40px;font-size:.78rem;color:#555;text-align:right;}}
  .recs-section {{margin-bottom:8px;}}
  .recs-section ol {{margin:0;padding-left:20px;}}
  .recs-section li {{margin-bottom:6px;font-size:.9rem;line-height:1.4;}}
  .footer {{background:#f9f9f9;border-top:1px solid #eee;padding:14px 32px;
            font-size:.75rem;color:#888;}}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>Full Harbor Parent Experience Report Card</h1>
    <h2>{html_lib.escape(club_name)}</h2>
    <div class="meta">{html_lib.escape(url)} &nbsp;&middot;&nbsp; Audited {audited}</div>
  </div>
  <div class="body">
    {login_wall_html}
    <div class="scores">
      <div class="score-box">
        <div class="label">Parent Experience Score</div>
        <div class="value">{s['found']}/{s['total']}
          <span class="grade" style="color:{_grade_color(parent_grade)}">{parent_grade}</span>
        </div>
        <div class="sub">{parent_pct}% of questions answered</div>
      </div>
      <div class="score-box">
        <div class="label">GEO / AIO Readiness</div>
        <div class="value">{geo.total_score}/{geo.max_score}
          <span class="grade" style="color:{_grade_color(geo.grade)}">{geo.grade}</span>
        </div>
        <div class="sub">AI &amp; search engine visibility</div>
      </div>
    </div>
    <table class="audit-table">
      {category_rows_html}
    </table>
    <div class="geo-section">
      <h3 class="section-title">GEO / AIO Dimension Breakdown</h3>
      {geo_bars_html}
    </div>
    <div class="recs-section">
      <h3 class="section-title">Top 3 Improvements</h3>
      <ol>{recs_html}</ol>
    </div>
  </div>
  <div class="footer">Generated by Full Harbor Auditor &mdash; fullharbor.org</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_report(
    url: str,
    club_name: str,
    club_slug: str = "unknown",
    page_type: str = "camp",
    output_format: str = "text",
    out_path: Optional[str] = None,
) -> str:
    """Run a full combined audit and return the formatted report string."""
    login_wall = is_login_wall(url)
    audit = audit_page(url, club_slug=club_slug, page_type=page_type)
    geo = score_url(url, club_slug=club_slug)
    recommendations = build_top_recommendations(audit, geo)

    if output_format == "html":
        report = format_html(club_name, url, audit, geo, login_wall, recommendations)
    else:
        report = format_text(club_name, url, audit, geo, login_wall, recommendations)

    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Report saved to: {out_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Full Harbor Combined Report Card")
    parser.add_argument("--url", required=True, help="Club program URL to audit")
    parser.add_argument("--club-name", default="Unknown Club", help="Display name for the club")
    parser.add_argument("--club-slug", default="unknown", help="Short club identifier")
    parser.add_argument("--page-type", default="camp", help="Page type: camp, hub, general")
    parser.add_argument(
        "--format", dest="output_format", choices=["text", "html"], default="text",
        help="Output format: text (default) or html",
    )
    parser.add_argument("--out", help="Save report to this file path instead of stdout")
    args = parser.parse_args()

    report = run_report(
        url=args.url,
        club_name=args.club_name,
        club_slug=args.club_slug,
        page_type=args.page_type,
        output_format=args.output_format,
        out_path=args.out,
    )
    if not args.out:
        print(report)


if __name__ == "__main__":
    main()
