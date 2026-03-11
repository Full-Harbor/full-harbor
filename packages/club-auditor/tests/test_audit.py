"""
Club Auditor unit tests — no network calls required.

Uses mock HTTP responses to test:
- 20-question parent experience scoring (audit.py)
- GEO/AIO readiness scoring (geo_scorer.py)
- Login wall / thin content detection
- Combined report card generation (reporter/report.py)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure club-auditor/src is on the path for all imports
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from analyzer.audit import audit_page, scrape_text, Score
from analyzer.geo_scorer import score_url, GEOScorer


# ---------------------------------------------------------------------------
# Mock HTML fixtures
# ---------------------------------------------------------------------------

RICH_CAMP_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Opti Summer Camp 2026 | Lakewood Yacht Club</title>
  <meta name="description" content="Youth sailing camp for beginners age 7-13, June 2026.">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
  <h1>Opti Summer Camp 2026</h1>
  <h2>What ages can attend?</h2>
  <p>Open to sailors ages 7 to 13. No experience required — beginners welcome!</p>
  <h2>Do I need to be a member?</h2>
  <p>Non-members are welcome. Member price: $740. Non-member price: $1,000.</p>
  <h2>When is camp?</h2>
  <p>June 8 - June 19, 2026. Monday through Friday, 9am to 3pm.</p>
  <h2>What should we bring?</h2>
  <p>Bring sunscreen, closed-toe shoes, lunch, and a water bottle.</p>
  <h2>Swimming</h2>
  <p>All participants must pass a swim test. Life jackets (PFDs) are provided.</p>
  <h2>Safety</h2>
  <p>US Sailing certified instructors. CPR and first aid trained staff on site.</p>
  <h2>Coaches</h2>
  <p>Led by Head Coach Jane Smith. Our coaches are US Sailing certified instructors.</p>
  <p>Coach-to-student ratio of 1:6.</p>
  <h2>Boats</h2>
  <p>Sailors will learn on Optimist (Opti) dinghies.</p>
  <h2>How do I register?</h2>
  <p>Register online at lakewoodyachtclub.com. Cancellation policy: full refund before June 1.</p>
  <h2>Year-round program</h2>
  <p>We offer a fall program and after-school sailing sessions.</p>
  <p>In case of lightning or bad weather, all sailors return to shore immediately.</p>
</body>
</html>"""

# Simulates a ClubSpot/member-only login wall — very little visible text
LOGIN_WALL_HTML = (
    "<html><body><p>Please log in to view this content.</p></body></html>"
)

# Minimal page with almost no useful content
MINIMAL_HTML = (
    "<html><head><title>Summer Camps</title></head>"
    "<body><p>Contact us for details about our summer camps.</p></body></html>"
)


def _mock_response(html: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = html
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# audit_page tests
# ---------------------------------------------------------------------------

class TestAuditPage:
    @patch("analyzer.audit.requests.get")
    def test_rich_page_scores_at_least_12(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        s = result.score_summary
        assert s["found"] >= 12, f"Expected >=12 found, got {s['found']}"

    @patch("analyzer.audit.requests.get")
    def test_login_wall_scores_zero(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(LOGIN_WALL_HTML)
        result = audit_page("https://example.com/locked", club_slug="hyc")
        assert result.score_summary["found"] == 0

    @patch("analyzer.audit.requests.get")
    def test_all_20_questions_in_result(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        assert len(result.questions) == 20

    @patch("analyzer.audit.requests.get")
    def test_all_scores_are_valid_enum_values(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        for q in result.questions:
            assert q.score in Score

    @patch("analyzer.audit.requests.get")
    def test_network_failure_returns_empty_questions(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("Connection refused")
        result = audit_page("https://unreachable.example.com/", club_slug="test")
        assert result.questions == []

    @patch("analyzer.audit.requests.get")
    def test_detects_ages(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        by_id = {q.question_id: q for q in result.questions}
        assert by_id[2].score == Score.FOUND, "Age question not detected"

    @patch("analyzer.audit.requests.get")
    def test_detects_pricing(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        by_id = {q.question_id: q for q in result.questions}
        assert by_id[4].score == Score.FOUND, "Pricing question not detected"

    @patch("analyzer.audit.requests.get")
    def test_detects_swim_requirement(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        by_id = {q.question_id: q for q in result.questions}
        assert by_id[8].score == Score.FOUND, "Swim question not detected"

    @patch("analyzer.audit.requests.get")
    def test_evidence_populated_for_found_questions(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        found_qs = [q for q in result.questions if q.score == Score.FOUND]
        for q in found_qs:
            assert q.evidence is not None, f"Q{q.question_id} FOUND but evidence is None"

    @patch("analyzer.audit.requests.get")
    def test_score_summary_totals_to_20(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        result = audit_page("https://example.com/opti-camp", club_slug="lyc")
        s = result.score_summary
        assert s["total"] == 20
        assert s["found"] + s["partial"] + s["not_found"] == 20


# ---------------------------------------------------------------------------
# GEO scorer tests
# ---------------------------------------------------------------------------

class TestGEOScorer:
    @patch("analyzer.geo_scorer.requests.get")
    def test_rich_page_scores_above_50(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        report = score_url("https://example.com/opti-camp", "lyc")
        assert report.total_score >= 50, f"Expected >=50, got {report.total_score}"

    @patch("analyzer.geo_scorer.requests.get")
    def test_login_wall_scores_at_most_15(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(LOGIN_WALL_HTML)
        report = score_url("https://example.com/locked", "hyc")
        assert report.total_score <= 15, f"Expected <=15 for login wall, got {report.total_score}"

    @patch("analyzer.geo_scorer.requests.get")
    def test_has_four_dimensions(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        report = score_url("https://example.com/opti-camp", "lyc")
        assert len(report.dimensions) == 4

    @patch("analyzer.geo_scorer.requests.get")
    def test_dimension_names(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        report = score_url("https://example.com/opti-camp", "lyc")
        names = {d.name for d in report.dimensions}
        assert "Structure" in names
        assert "Content Completeness" in names
        assert "Technical" in names
        assert "Freshness" in names

    @patch("analyzer.geo_scorer.requests.get")
    def test_network_failure_returns_zero_score(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("Timeout")
        report = score_url("https://unreachable.example.com/", "test")
        assert report.total_score == 0

    @patch("analyzer.geo_scorer.requests.get")
    def test_grade_is_valid_letter(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        report = score_url("https://example.com/opti-camp", "lyc")
        assert report.grade in {"A", "B", "C", "D", "F"}

    @patch("analyzer.geo_scorer.requests.get")
    def test_total_does_not_exceed_max(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        report = score_url("https://example.com/opti-camp", "lyc")
        assert report.total_score <= report.max_score

    def test_geo_scorer_class_instantiates(self) -> None:
        scorer = GEOScorer()
        assert scorer is not None

    @patch("analyzer.geo_scorer.requests.get")
    def test_geo_scorer_class_score_method(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        scorer = GEOScorer()
        report = scorer.score("https://example.com/opti-camp", "lyc")
        assert report.total_score >= 50


# ---------------------------------------------------------------------------
# Login wall detection tests
# ---------------------------------------------------------------------------

class TestLoginWallDetection:
    @patch("analyzer.audit.requests.get")
    def test_thin_content_below_threshold(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(LOGIN_WALL_HTML)
        from reporter.report import LOGIN_WALL_THRESHOLD
        text = scrape_text("https://example.com/locked")
        assert text is not None
        assert len(text.strip()) < LOGIN_WALL_THRESHOLD

    @patch("analyzer.audit.requests.get")
    def test_rich_content_above_threshold(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import LOGIN_WALL_THRESHOLD
        text = scrape_text("https://example.com/opti-camp")
        assert text is not None
        assert len(text.strip()) >= LOGIN_WALL_THRESHOLD

    @patch("analyzer.audit.requests.get")
    def test_is_login_wall_returns_true_for_thin_content(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(LOGIN_WALL_HTML)
        from reporter.report import is_login_wall
        assert is_login_wall("https://example.com/locked") is True

    @patch("analyzer.audit.requests.get")
    def test_is_login_wall_returns_false_for_rich_content(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import is_login_wall
        assert is_login_wall("https://example.com/opti-camp") is False

    @patch("analyzer.audit.requests.get")
    def test_is_login_wall_returns_true_on_network_failure(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("Connection refused")
        from reporter.report import is_login_wall
        assert is_login_wall("https://unreachable.example.com/") is True


# ---------------------------------------------------------------------------
# Report generation tests
# ---------------------------------------------------------------------------

class TestReportGeneration:
    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_text_report_has_key_sections(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(RICH_CAMP_HTML)
        mock_geo_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import run_report
        report = run_report(
            url="https://example.com/opti-camp",
            club_name="Test Yacht Club",
            club_slug="test",
            output_format="text",
        )
        assert "FULL HARBOR PARENT EXPERIENCE REPORT CARD" in report
        assert "PARENT EXPERIENCE SCORE" in report
        assert "GEO/AIO READINESS" in report
        assert "TOP 3 IMPROVEMENTS" in report
        assert "Test Yacht Club" in report

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_html_report_is_valid_html(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(RICH_CAMP_HTML)
        mock_geo_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import run_report
        report = run_report(
            url="https://example.com/opti-camp",
            club_name="Test Yacht Club",
            club_slug="test",
            output_format="html",
        )
        assert "<!DOCTYPE html>" in report
        assert "<html" in report
        assert "</html>" in report
        assert "<title>" in report
        assert "Test Yacht Club" in report

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_html_contains_both_scores(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(RICH_CAMP_HTML)
        mock_geo_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import run_report
        report = run_report(
            url="https://example.com/opti-camp",
            club_name="Test Yacht Club",
            club_slug="test",
            output_format="html",
        )
        assert "Parent Experience Score" in report
        assert "GEO / AIO Readiness" in report

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_login_wall_flagged_in_text_report(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(LOGIN_WALL_HTML)
        mock_geo_get.return_value = _mock_response(LOGIN_WALL_HTML)
        from reporter.report import run_report
        report = run_report(
            url="https://example.com/locked",
            club_name="Houston Yacht Club",
            club_slug="hyc",
            output_format="text",
        )
        assert "PLATFORM VISIBILITY RISK" in report

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_login_wall_flagged_in_html_report(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(LOGIN_WALL_HTML)
        mock_geo_get.return_value = _mock_response(LOGIN_WALL_HTML)
        from reporter.report import run_report
        report = run_report(
            url="https://example.com/locked",
            club_name="Houston Yacht Club",
            club_slug="hyc",
            output_format="html",
        )
        assert "risk-banner" in report
        assert "PLATFORM VISIBILITY RISK" in report

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_rich_page_not_flagged_as_login_wall(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(RICH_CAMP_HTML)
        mock_geo_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import run_report
        report = run_report(
            url="https://example.com/opti-camp",
            club_name="Lakewood Yacht Club",
            club_slug="lyc",
            output_format="text",
        )
        assert "PLATFORM VISIBILITY RISK" not in report

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_recommendations_present_in_text_report(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(MINIMAL_HTML)
        mock_geo_get.return_value = _mock_response(MINIMAL_HTML)
        from reporter.report import run_report
        report = run_report(
            url="https://example.com/minimal",
            club_name="Tiny Sailing Club",
            club_slug="tsc",
            output_format="text",
        )
        assert "TOP 3 IMPROVEMENTS" in report
        # Should have at least 1 numbered recommendation
        assert "1." in report

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_report_saved_to_file(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock, tmp_path: Path
    ) -> None:
        mock_audit_get.return_value = _mock_response(RICH_CAMP_HTML)
        mock_geo_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import run_report
        out_file = tmp_path / "report.txt"
        run_report(
            url="https://example.com/opti-camp",
            club_name="Test Yacht Club",
            club_slug="test",
            output_format="text",
            out_path=str(out_file),
        )
        assert out_file.exists()
        content = out_file.read_text()
        assert "FULL HARBOR PARENT EXPERIENCE REPORT CARD" in content

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_html_report_saved_to_file(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock, tmp_path: Path
    ) -> None:
        mock_audit_get.return_value = _mock_response(RICH_CAMP_HTML)
        mock_geo_get.return_value = _mock_response(RICH_CAMP_HTML)
        from reporter.report import run_report
        out_file = tmp_path / "report.html"
        run_report(
            url="https://example.com/opti-camp",
            club_name="Test Yacht Club",
            club_slug="test",
            output_format="html",
            out_path=str(out_file),
        )
        assert out_file.exists()
        content = out_file.read_text()
        assert "<!DOCTYPE html>" in content


# ---------------------------------------------------------------------------
# Recommendation builder tests
# ---------------------------------------------------------------------------

class TestRecommendationBuilder:
    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_returns_at_most_3_recommendations(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(MINIMAL_HTML)
        mock_geo_get.return_value = _mock_response(MINIMAL_HTML)
        from reporter.report import build_top_recommendations
        audit = audit_page("https://example.com/minimal", club_slug="test")
        geo = score_url("https://example.com/minimal", "test")
        recs = build_top_recommendations(audit, geo, top_n=3)
        assert len(recs) <= 3

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_recommendations_are_strings(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(MINIMAL_HTML)
        mock_geo_get.return_value = _mock_response(MINIMAL_HTML)
        from reporter.report import build_top_recommendations
        audit = audit_page("https://example.com/minimal", club_slug="test")
        geo = score_url("https://example.com/minimal", "test")
        recs = build_top_recommendations(audit, geo)
        for rec in recs:
            assert isinstance(rec, str)
            assert len(rec) > 0

    @patch("analyzer.geo_scorer.requests.get")
    @patch("analyzer.audit.requests.get")
    def test_no_duplicate_recommendations(
        self, mock_audit_get: MagicMock, mock_geo_get: MagicMock
    ) -> None:
        mock_audit_get.return_value = _mock_response(MINIMAL_HTML)
        mock_geo_get.return_value = _mock_response(MINIMAL_HTML)
        from reporter.report import build_top_recommendations
        audit = audit_page("https://example.com/minimal", club_slug="test")
        geo = score_url("https://example.com/minimal", "test")
        recs = build_top_recommendations(audit, geo, top_n=10)
        assert len(recs) == len(set(recs)), "Duplicate recommendations found"
