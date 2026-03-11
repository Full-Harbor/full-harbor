"""
Club Auditor — GEO/AIO Readiness Scorer
=========================================
Measures how well a club website will perform in AI-mediated search.

GEO = Generative Engine Optimization (how AI summarizers retrieve content)
AIO = AI Overview (Google's AI-generated answer boxes)

The same content that makes Google's AI Overviews work is what makes
ChatGPT, Perplexity, and Claude give accurate answers about your club.

"Whether parents Google or ask ChatGPT, the answer comes from the same
place — your website. Be invisible there, be invisible everywhere."
— Full Harbor

Scoring dimensions (100 points total):

  STRUCTURE (30 pts)
  ├── Clear <h1> with club + program name         10
  ├── Pricing in parseable format (table or list)  10
  └── FAQ-style Q&A markup or headers              10

  CONTENT COMPLETENESS (40 pts)
  ├── Price published (not "contact for pricing")  15
  ├── Dates published                               10
  ├── Ages/eligibility stated                       10
  └── Contact info (name + email + phone)           5

  TECHNICAL (20 pts)
  ├── <title> tag is descriptive (not "Home")       5
  ├── <meta description> present                    5
  ├── Schema.org markup (Event, EducationalEvent)   5
  └── Mobile-friendly indicators                    5

  FRESHNESS (10 pts)
  ├── Current year mentioned                        5
  └── Dates are future (not past events)            5

Usage:
  python geo_scorer.py --url https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026
  python geo_scorer.py --club all --output-format json
"""

import re
import json
import argparse
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
from bs4 import BeautifulSoup


CURRENT_YEAR = datetime.now().year
HEADERS = {"User-Agent": "FullHarborAuditor/1.0 (+https://fullharbor.org/auditor)"}


# ---------------------------------------------------------------------------
# Score Dimensions
# ---------------------------------------------------------------------------

@dataclass
class GEODimension:
    name: str
    max_points: int
    earned: int = 0
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    @property
    def pct(self) -> float:
        return round(100 * self.earned / self.max_points) if self.max_points else 0


@dataclass
class GEOReport:
    url: str
    club_slug: str
    scored_at: str
    total_score: int
    max_score: int = 100
    dimensions: list[GEODimension] = field(default_factory=list)
    top_recommendations: list[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        pct = self.pct_score
        if pct >= 85: return "A"
        if pct >= 70: return "B"
        if pct >= 55: return "C"
        if pct >= 40: return "D"
        return "F"

    @property
    def pct_score(self) -> float:
        return round(100 * self.total_score / self.max_score) if self.max_score else 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def fetch_soup(url: str) -> Optional[tuple[BeautifulSoup, str]]:
    """Fetch URL and return (BeautifulSoup, raw_text)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        raw = soup.get_text(separator=" ", strip=True)
        return soup, raw
    except Exception as e:
        print(f"  ⚠️  Failed to fetch {url}: {e}")
        return None, None


def score_structure(soup: BeautifulSoup, raw: str) -> GEODimension:
    dim = GEODimension("Structure", max_points=30)

    # H1 with meaningful content
    h1 = soup.find("h1")
    if h1 and len(h1.get_text(strip=True)) > 10:
        dim.earned += 10
        dim.evidence.append(f"H1: '{h1.get_text(strip=True)[:60]}'")
    else:
        dim.gaps.append("No descriptive <h1> tag — AI summarizers use this as the page title")

    # Pricing in structured format (table, list, or clearly formatted)
    price_in_table = soup.find("table") and re.search(r"\$\d+", soup.find("table").get_text() if soup.find("table") else "")
    price_in_list = soup.find("ul") and re.search(r"\$\d+", " ".join(li.get_text() for li in soup.find_all("li")))
    price_formatted = re.search(r"(member|non-?member)[^\n]{0,30}\$\d+", raw, re.IGNORECASE)

    if price_in_table:
        dim.earned += 10
        dim.evidence.append("Pricing found in <table> format — excellent for AI extraction")
    elif price_in_list or price_formatted:
        dim.earned += 6
        dim.evidence.append("Pricing in list/inline format — AI can usually extract this")
    else:
        dim.gaps.append("Pricing not in structured format — use a table or labeled list")

    # FAQ or Q&A structure
    faq_headers = [h for h in soup.find_all(["h2", "h3", "h4"])
                   if re.search(r"(FAQ|question|what|how|when|where|who|can I|do I)", h.get_text(), re.IGNORECASE)]
    if len(faq_headers) >= 2:
        dim.earned += 10
        dim.evidence.append(f"{len(faq_headers)} FAQ-style headers found — strong AI signal")
    elif len(faq_headers) == 1:
        dim.earned += 5
        dim.evidence.append("1 FAQ-style header found — add more Q&A sections")
    else:
        dim.gaps.append("No FAQ/Q&A markup — parents ask questions; your page should answer them in question form")

    return dim


def score_content(soup: BeautifulSoup, raw: str) -> GEODimension:
    dim = GEODimension("Content Completeness", max_points=40)

    # Price published
    if re.search(r"\$\d+", raw):
        prices = re.findall(r"\$[\d,]+", raw)
        dim.earned += 15
        dim.evidence.append(f"Pricing found: {', '.join(prices[:3])}")
    else:
        dim.gaps.append("CRITICAL: No pricing found — this is the #1 question parents ask")

    # Dates published and current
    date_match = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}",
        raw, re.IGNORECASE
    )
    year_match = re.search(r"\b(202[5-9]|203\d)\b", raw)
    if date_match and year_match:
        dim.earned += 10
        dim.evidence.append(f"Dates with year found: '{date_match.group(0)} {year_match.group(0)}'")
    elif date_match or year_match:
        dim.earned += 5
        dim.evidence.append("Partial date info found — add full month/day/year")
    else:
        dim.gaps.append("No dates found — parents need to know exactly when camp runs")

    # Ages/eligibility
    age_match = re.search(r"age[s]?\s*:?\s*\d|ages?\s+\d+\s*(to|-)\s*\d+|grade[s]?\s+\d", raw, re.IGNORECASE)
    if age_match:
        dim.earned += 10
        dim.evidence.append(f"Age eligibility found: '{age_match.group(0)}'")
    else:
        dim.gaps.append("No age eligibility info — parents need to know if their child qualifies")

    # Contact info (name + contact method)
    has_email = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", raw)
    has_phone = re.search(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", raw)
    has_name = re.search(r"(director|coordinator|contact|coach)\s*:?\s*[A-Z][a-z]+ [A-Z][a-z]+", raw, re.IGNORECASE)

    contact_score = 0
    if has_email: contact_score += 2
    if has_phone: contact_score += 2
    if has_name: contact_score += 1
    dim.earned += contact_score

    if contact_score >= 4:
        dim.evidence.append("Contact info complete (email + phone)")
    elif contact_score > 0:
        dim.evidence.append("Partial contact info — add both email and phone")
    else:
        dim.gaps.append("No contact info — who does a parent call with questions?")

    return dim


def score_technical(soup: BeautifulSoup, raw: str) -> GEODimension:
    dim = GEODimension("Technical", max_points=20)

    # Title tag
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    if title_tag and len(title_text) > 20 and title_text.lower() not in ("home", "untitled", "welcome"):
        dim.earned += 5
        dim.evidence.append(f"<title>: '{title_text[:60]}'")
    else:
        dim.gaps.append(f"Generic/missing <title> tag: '{title_text[:40]}' — use 'Program Name | Club Name | Year'")

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content") and len(meta_desc["content"]) > 30:
        dim.earned += 5
        dim.evidence.append(f"Meta description: '{meta_desc['content'][:60]}'")
    else:
        dim.gaps.append("No meta description — this is what Google and AI use as the page summary")

    # Schema.org structured data
    schema_tags = soup.find_all("script", attrs={"type": "application/ld+json"})
    if schema_tags:
        for tag in schema_tags:
            try:
                data = json.loads(tag.string or "")
                schema_type = data.get("@type", "")
                if schema_type in ("Event", "EducationalEvent", "Course", "SportsEvent"):
                    dim.earned += 5
                    dim.evidence.append(f"Schema.org markup found: @type={schema_type}")
                    break
            except Exception:
                pass
    else:
        dim.gaps.append("No Schema.org structured data — adding Event or EducationalEvent markup significantly boosts AI extraction")

    # Viewport meta (mobile-friendly proxy)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport:
        dim.earned += 5
        dim.evidence.append("Viewport meta tag present (mobile-friendly)")
    else:
        dim.gaps.append("No viewport meta tag — mobile optimization affects search ranking")

    return dim


def score_freshness(soup: BeautifulSoup, raw: str) -> GEODimension:
    dim = GEODimension("Freshness", max_points=10)
    current_year_str = str(CURRENT_YEAR)

    # Current year mentioned
    if current_year_str in raw:
        dim.earned += 5
        dim.evidence.append(f"Current year ({current_year_str}) found on page")
    else:
        dim.gaps.append(f"Year {current_year_str} not found — AI may treat this as outdated content")

    # Future dates (not all in the past)
    future_months = []
    current_month = datetime.now().month
    for month_num, month_name in enumerate(
        ["january","february","march","april","may","june",
         "july","august","september","october","november","december"], 1
    ):
        if re.search(rf"{month_name}\s+\d{{1,2}}", raw, re.IGNORECASE) and month_num >= current_month:
            future_months.append(month_name)

    if future_months:
        dim.earned += 5
        dim.evidence.append(f"Future dates found: {', '.join(future_months[:3])}")
    else:
        dim.gaps.append("No upcoming dates found — content may appear stale to AI systems")

    return dim


def score_url(url: str, club_slug: str) -> GEOReport:
    """Run the full GEO/AIO readiness score on a URL."""
    soup, raw = fetch_soup(url)
    if soup is None:
        return GEOReport(
            url=url,
            club_slug=club_slug,
            scored_at=datetime.utcnow().isoformat(),
            total_score=0,
        )

    dims = [
        score_structure(soup, raw),
        score_content(soup, raw),
        score_technical(soup, raw),
        score_freshness(soup, raw),
    ]

    total = sum(d.earned for d in dims)

    # Build top recommendations from gaps
    all_gaps = [(d.name, g) for d in dims for g in d.gaps]
    # Prioritize content gaps (most impactful)
    priority_order = ["Content Completeness", "Structure", "Technical", "Freshness"]
    all_gaps.sort(key=lambda x: priority_order.index(x[0]) if x[0] in priority_order else 99)
    top_recs = [g for _, g in all_gaps[:5]]

    return GEOReport(
        url=url,
        club_slug=club_slug,
        scored_at=datetime.utcnow().isoformat(),
        total_score=total,
        dimensions=dims,
        top_recommendations=top_recs,
    )


def print_geo_report(report: GEOReport):
    print(f"\n{'='*65}")
    print(f"GEO/AIO READINESS: {report.club_slug.upper()}")
    print(f"URL: {report.url}")
    print(f"{'='*65}")
    print(f"Score: {report.total_score}/{report.max_score} — Grade: {report.grade}")
    print()

    for dim in report.dimensions:
        bar = "█" * (dim.earned // 2) + "░" * ((dim.max_points - dim.earned) // 2)
        print(f"  {dim.name:<25} {dim.earned:>3}/{dim.max_points:<3} |{bar}|")
        for e in dim.evidence:
            print(f"    ✅ {e}")
        for g in dim.gaps:
            print(f"    ❌ {g[:80]}")

    if report.top_recommendations:
        print(f"\n  TOP IMPROVEMENTS:")
        for i, rec in enumerate(report.top_recommendations[:3], 1):
            print(f"  {i}. {rec}")


CLUB_AUDIT_URLS = {
    "lyc": "https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
    "hyc": "https://www.houstonyachtclub.com/summer-camps",
    "tcyc": "https://www.tcyc.org",
}


def main():
    parser = argparse.ArgumentParser(description="GEO/AIO Readiness Scorer")
    parser.add_argument("--url", help="Score a specific URL")
    parser.add_argument("--club", choices=["lyc", "hyc", "tcyc", "all"])
    parser.add_argument("--club-slug", default="unknown")
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.url:
        report = score_url(args.url, args.club_slug)
        if args.output_format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_geo_report(report)

    elif args.club:
        clubs = list(CLUB_AUDIT_URLS.keys()) if args.club == "all" else [args.club]
        reports = []
        for slug in clubs:
            report = score_url(CLUB_AUDIT_URLS[slug], slug)
            reports.append(report)
            if args.output_format == "text":
                print_geo_report(report)

        if args.club == "all" and args.output_format == "text":
            print(f"\n\n{'='*65}")
            print("GEO/AIO READINESS COMPARISON")
            print(f"{'='*65}")
            print(f"{'Club':<10} {'Score':>7} {'Grade':>7}  Top Gap")
            print("-" * 65)
            for r in reports:
                top_gap = r.top_recommendations[0][:45] if r.top_recommendations else "—"
                print(f"{r.club_slug:<10} {r.total_score:>5}/{r.max_score:<3} {r.grade:>5}   {top_gap}")
    else:
        parser.print_help()


class GEOScorer:
    """Convenience class wrapper around the module-level score_url function."""

    def score(self, url: str, club_slug: str = "unknown") -> GEOReport:
        """Score a URL for GEO/AIO readiness."""
        return score_url(url, club_slug)


if __name__ == "__main__":
    main()
