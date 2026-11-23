import pytest

from services.deal_math import DealInputs, analyze, deal_score, monthly_payment


def test_monthly_payment_matches_amortization_formula():
    assert monthly_payment(200_000, 6.0, 30) == pytest.approx(1199.10, abs=0.01)
    assert monthly_payment(120_000, 0, 10) == pytest.approx(1000.0)
    assert monthly_payment(0, 7, 30) == 0


def _deal(**overrides):
    base = dict(
        price=200_000, monthly_rent=2_000, annual_tax=4_000, annual_insurance=1_200, monthly_hoa=0,
        down_payment_pct=25, interest_rate_pct=7.0, loan_years=30, closing_cost_pct=3,
        vacancy_pct=8, maintenance_pct=8, capex_pct=8, management_pct=0,
    )
    base.update(overrides)
    return DealInputs(**base)


def test_noi_and_cashflow():
    result = analyze(_deal())
    # 24,000 rent * (1 - 0.24) - 4,000 tax - 1,200 insurance
    assert result.annual_noi == pytest.approx(13_040)
    assert result.cap_rate == pytest.approx(0.0652)
    expected_pi = monthly_payment(150_000, 7.0, 30)
    assert result.monthly_cashflow == pytest.approx(13_040 / 12 - expected_pi, abs=0.01)
    assert result.cash_invested == pytest.approx(56_000)


def test_zero_values_are_respected_not_defaulted():
    assert analyze(_deal(vacancy_pct=0, maintenance_pct=0, capex_pct=0)).annual_noi == pytest.approx(18_800)


def test_deal_score_bounds():
    assert deal_score(0.2, 0.3, 0.5, 200) == 100
    assert 0 <= deal_score(-0.05, -0.5, -1, 0) <= 10
