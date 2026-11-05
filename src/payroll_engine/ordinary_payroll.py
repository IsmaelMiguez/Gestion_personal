"""Base-only ordinary payment: full month, full time, indefinite contract.

Monthly contribution groups 1–7 only; no special systems, rebates or
additional retirement contributions. Extra payments are accrued equally
and contributed monthly, but their actual payment is outside this result.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from . import rules_2026 as rules
from .base_salary import (
    CENT,
    BaseSalaryBreakdown,
    _calculation_context,
    base_salary_from_annual,
)


class InvalidPayrollInput(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Contribution:
    name: str
    base: Decimal
    employee_rate: Decimal
    employer_rate: Decimal
    employee_amount: Decimal
    employer_amount: Decimal


@dataclass(frozen=True, slots=True)
class OrdinaryPayroll:
    salary: BaseSalaryBreakdown
    extra_payment_accrual: Decimal
    uncapped_contribution_base: Decimal
    common_contribution_base: Decimal
    professional_contribution_base: Decimal
    contributions: tuple[Contribution, ...]
    employee_contributions: Decimal
    employer_contributions: Decimal
    withholding_rate: Decimal
    withholding_amount: Decimal
    net_amount: Decimal
    employer_cash_cost: Decimal


def _validate_rate(value: Decimal, field: str) -> None:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or not Decimal(0) <= value <= Decimal(100)
        or value != value.quantize(CENT)
    ):
        raise InvalidPayrollInput(
            field, "Indica un Decimal entre 0 y 100, con hasta dos decimales."
        )


def _contribution(
    name: str, base: Decimal, rates: tuple[Decimal, Decimal]
) -> Contribution:
    employee_rate, employer_rate = rates
    return Contribution(
        name,
        base,
        employee_rate,
        employer_rate,
        (base * employee_rate / 100).quantize(CENT),
        (base * employer_rate / 100).quantize(CENT),
    )


def _contributions(
    common_base: Decimal,
    professional_base: Decimal,
    uncapped_base: Decimal,
    occupational_risk_rate: Decimal,
) -> tuple[Contribution, ...]:
    lines = [
        _contribution(
            "Contingencias comunes", common_base, rules.COMMON_RATES
        ),
        _contribution("MEI", common_base, rules.MEI_RATES),
        _contribution(
            "Desempleo", professional_base, rules.UNEMPLOYMENT_RATES
        ),
        _contribution(
            "Formación profesional", professional_base, rules.TRAINING_RATES
        ),
        _contribution("FOGASA", professional_base, rules.FOGASA_RATES),
        _contribution(
            "AT/EP", professional_base, (Decimal(0), occupational_risk_rate)
        ),
    ]
    for index, (lower, upper, employee_rate, employer_rate) in enumerate(
        rules.SOLIDARITY_BANDS, start=1
    ):
        base = max(Decimal("0.00"), min(uncapped_base, upper) - lower)
        lines.append(
            _contribution(
                f"Solidaridad {index}", base, (employee_rate, employer_rate)
            )
        )
    return tuple(lines)


def calculate_ordinary_payroll_2026(
    annual_base_salary: Decimal,
    payments_per_year: int,
    contribution_group: int,
    withholding_rate: Decimal,
    occupational_risk_rate: Decimal,
    rounding: str,
) -> OrdinaryPayroll:
    """Calculate an ordinary payment; all inputs and rounding are explicit.

    IRPF is applied to paid gross salary (RIRPF article 80), not to salary
    after Social Security deductions. Its rate must already be determined.
    Cost means this ordinary cash gross plus employer contributions; it does
    not include accrued extra payments, which are returned separately.
    """
    with localcontext(_calculation_context(rounding)):
        salary = base_salary_from_annual(
            annual_base_salary, payments_per_year, rounding
        )
        if (
            type(contribution_group) is not int
            or not 1 <= contribution_group <= 7
        ):
            raise InvalidPayrollInput(
                "contribution_group",
                "Este caso admite grupos mensuales 1 a 7.",
            )
        _validate_rate(withholding_rate, "withholding_rate")
        _validate_rate(occupational_risk_rate, "occupational_risk_rate")
        accrual = (
            salary.extra_payment_amount * salary.extra_payments_per_year / 12
        ).quantize(CENT)
        gross = salary.ordinary_payment_amount
        uncapped = gross + accrual
        common = min(
            rules.MAXIMUM_BASE,
            max(rules.MONTHLY_MINIMUM_BASES[contribution_group - 1], uncapped),
        )
        professional = min(
            rules.MAXIMUM_BASE, max(rules.MINIMUM_PROFESSIONAL_BASE, uncapped)
        )
        lines = _contributions(
            common, professional, uncapped, occupational_risk_rate
        )
        employee_total = sum(
            (line.employee_amount for line in lines), Decimal("0.00")
        )
        employer_total = sum(
            (line.employer_amount for line in lines), Decimal("0.00")
        )
        withholding = (gross * withholding_rate / 100).quantize(CENT)
        return OrdinaryPayroll(
            salary,
            accrual,
            uncapped,
            common,
            professional,
            lines,
            employee_total,
            employer_total,
            withholding_rate,
            withholding,
            gross - employee_total - withholding,
            gross + employer_total,
        )
