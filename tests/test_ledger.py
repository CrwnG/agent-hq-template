import pytest

from hq import config, ledger


def test_empty_ledger_is_honest_zero():
    s = ledger.money_summary()
    assert s["revenue_cents"] == 0 and s["profit_cents"] == 0 and s["invested_cents"] == 0
    assert s["goals_cents"] == []  # no goal configured -> no goal bar


def test_profit_excludes_investment_and_payout():
    ledger.add_entry("sale", 2500, "stripe")
    ledger.add_entry("fee", -250, "stripe")
    ledger.add_entry("investment", -1500, "other")
    ledger.add_entry("payout", 2000, "stripe")
    s = ledger.money_summary()
    assert s["revenue_cents"] == 2500
    assert s["profit_cents"] == 2250
    assert s["invested_cents"] == 1500
    assert s["month_profit_cents"] == 2250


def test_manual_sign_follows_kind_and_dedupes():
    row = ledger.add_manual("cost", 999, "Hosting Co", ref="inv-7")
    assert row["amount_cents"] == -999 and row["platform"] == "hosting_co"
    with pytest.raises(KeyError):
        ledger.add_manual("cost", 999, "hosting_co", ref="inv-7")
    with pytest.raises(ValueError):
        ledger.add_manual("sale", 0, "stripe")
    with pytest.raises(ValueError):
        ledger.add_entry("gift", 100, "stripe")


def test_month_pnl_by_platform():
    ledger.add_entry("sale", 5000, "stripe", ts="2026-09-03T12:00:00+00:00")
    ledger.add_entry("refund", -1000, "stripe", ts="2026-09-04T12:00:00+00:00")
    ledger.add_entry("cost", -700, "hosting", ts="2026-09-05T12:00:00+00:00")
    ledger.add_entry("sale", 9999, "stripe", ts="2026-08-30T12:00:00+00:00")  # other month
    p = ledger.month_pnl("2026-09")
    plats = {x["platform"]: x for x in p["platforms"]}
    assert plats["stripe"]["net"] == 4000 and plats["hosting"]["costs"] == -700
    assert p["totals"]["net"] == 3300 and p["totals"]["entries"] == 3


def test_goal_ladder_has_floor_and_no_ceiling():
    assert ledger.goal_ladder(0, 20000) == [20000, 40000, 60000]
    assert ledger.goal_ladder(-500, 20000) == [20000, 40000, 60000]
    assert ledger.goal_ladder(45000, 20000) == [40000, 60000, 80000]
    assert ledger.goal_ladder(12345, 0) == []


def test_goal_from_config(monkeypatch):
    monkeypatch.setenv("HQ_GOAL_CENTS", "20000")
    assert config.goal_cents() == 20000
    assert ledger.money_summary()["goals_cents"] == [20000, 40000, 60000]


@pytest.mark.parametrize("raw,cents", [("12.50", 1250), ("$1,000", 100000), (".5", 50), (7, 700)])
def test_dollars_to_cents(raw, cents):
    assert ledger.dollars_to_cents(raw) == cents


@pytest.mark.parametrize("raw", ["-5", "0", "1.234", "abc", "", "10000000"])
def test_dollars_to_cents_rejects(raw):
    with pytest.raises(ValueError):
        ledger.dollars_to_cents(raw)
