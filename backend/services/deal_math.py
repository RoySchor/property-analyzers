"""Pure investment math so it can be unit tested without a database."""

from dataclasses import dataclass


@dataclass
class DealInputs:
    price: float
    monthly_rent: float
    annual_tax: float
    annual_insurance: float
    monthly_hoa: float
    down_payment_pct: float     # 25 means 25%
    interest_rate_pct: float    # 7.0 means 7%
    loan_years: int
    closing_cost_pct: float
    vacancy_pct: float
    maintenance_pct: float
    capex_pct: float
    management_pct: float


@dataclass
class DealResult:
    monthly_principal_interest: float
    monthly_piti: float
    annual_noi: float
    monthly_cashflow: float
    cap_rate: float
    cash_on_cash: float
    cash_invested: float


def monthly_payment(principal: float, annual_rate_pct: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    monthly_rate = annual_rate_pct / 100 / 12
    payments = years * 12
    if monthly_rate == 0:
        return principal / payments
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -payments)


def analyze(deal: DealInputs) -> DealResult:
    loan = deal.price * (1 - deal.down_payment_pct / 100)
    principal_interest = monthly_payment(loan, deal.interest_rate_pct, deal.loan_years)
    gross_rent = deal.monthly_rent * 12
    variable_expense_pct = (deal.vacancy_pct + deal.maintenance_pct + deal.capex_pct + deal.management_pct) / 100
    noi = gross_rent * (1 - variable_expense_pct) - deal.annual_tax - deal.annual_insurance - deal.monthly_hoa * 12
    cashflow = noi / 12 - principal_interest
    cash_invested = deal.price * (deal.down_payment_pct + deal.closing_cost_pct) / 100
    piti = principal_interest + (deal.annual_tax + deal.annual_insurance) / 12 + deal.monthly_hoa
    return DealResult(
        monthly_principal_interest=round(principal_interest, 2),
        monthly_piti=round(piti, 2),
        annual_noi=round(noi, 2),
        monthly_cashflow=round(cashflow, 2),
        cap_rate=noi / deal.price if deal.price else 0.0,
        cash_on_cash=(cashflow * 12) / cash_invested if cash_invested else 0.0,
        cash_invested=round(cash_invested, 2),
    )


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def deal_score(cap_rate: float, cash_on_cash: float, comp_discount: float | None, days_on_market: float | None) -> float:
    """0-100. Weights: cap rate 40, cash-on-cash 30, price vs comps 20, negotiating room (days on market) 10."""
    score = 40 * clamp01(cap_rate / 0.10)
    score += 30 * clamp01((cash_on_cash + 0.05) / 0.17)
    score += 20 * (clamp01((comp_discount + 0.10) / 0.30) if comp_discount is not None else 0.5)
    score += 10 * (clamp01(days_on_market / 90) if days_on_market is not None else 0.3)
    return round(score, 1)
