"""Kiểm thử tích hợp engine VNEquity với API của giao diện (chạy offline bằng dữ liệu mẫu FPT).

    python -m pytest tests -q
"""
import os

os.environ.setdefault("VNEQUITY_OFFLINE", "1")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

client = TestClient(app)
PAYLOAD = {
    "ticker": "FPT", "horizon_months": 12,
    "horizon_thresholds_pct": {"3": {"buy": 5, "sell": -5}, "6": {"buy": 8, "sell": -8}, "12": {"buy": 12, "sell": -10}},
    "buy_threshold_pct": 12, "sell_threshold_pct": -10, "dividend_yield_pct": 0,
    "probabilities_pct": {"bullish": 25, "base": 50, "bearish": 25},
    "sensitivity_growth_pct": [0, 10, 20], "sensitivity_pe": [10, 15, 20],
}


def test_live_schema_matches_frontend():
    r = client.post("/api/scenario/live", json=PAYLOAD)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [s["key"] for s in d["scenarios"]] == ["bullish", "base", "bearish"]
    for s in d["scenarios"]:
        for f in ("label", "earnings_growth_pct", "target_pe", "projected_eps", "estimated_price",
                  "expected_return_pct", "assessment", "assumption_basis", "evidence"):
            assert f in s
        for card in s["evidence"]:
            assert {"claim", "value", "unit", "formula", "source", "period"} <= set(card)
    by = {s["key"]: s for s in d["scenarios"]}
    assert by["bullish"]["estimated_price"] > by["base"]["estimated_price"] > by["bearish"]["estimated_price"]
    # Giá = EPS dự phóng × P/E
    b = by["base"]
    assert abs(b["projected_eps"] * b["target_pe"] - b["estimated_price"]) / b["estimated_price"] < 0.002
    assert d["data_confidence"]["score"] >= 70
    assert len(d["sensitivity_grid"]["cells"]) == 3


def test_override_and_probability():
    q = dict(PAYLOAD, overrides={"bullish": {"earnings_growth_pct": 30, "target_pe": 20}},
             probabilities_pct={"bullish": 40, "base": 40, "bearish": 20})
    d = client.post("/api/scenario/live", json=q).json()
    bull = d["scenarios"][0]
    assert bull["earnings_growth_pct"] == 30 and bull["target_pe"] == 20
    exp = sum(s["estimated_price"] * p for s, p in zip(d["scenarios"], (0.4, 0.4, 0.2)))
    assert abs(exp - d["probability_weighted_value"]) < 2


def test_pdf_purposes():
    for purpose, groups in (("full", []), ("one_pager", ["executive_summary", "scenario"]), ("trader", ["market_risk"])):
        r = client.post("/api/scenario/live/report.pdf",
                        json=dict(PAYLOAD, report={"purpose": purpose, "metric_groups": groups, "detail_level": "standard", "include_chart": True}))
        assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_bad_probabilities_rejected():
    r = client.post("/api/scenario/live", json=dict(PAYLOAD, probabilities_pct={"bullish": 50, "base": 50, "bearish": 50}))
    assert r.status_code == 422
