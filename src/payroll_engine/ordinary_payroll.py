"""Ordinary payment: full month, full time, indefinite contract.

Monthly contribution groups 1–7 only; no special systems, rebates or
additional retirement contributions. Estimated annual extras contribute
monthly, but their actual payment is outside this result.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from . import rules_2026 as rules
from .base_salary import (
    CENT,
    MAX_INPUT_AMOUNT,
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
    seniority_amount: Decimal
    gross_amount: Decimal
    insurance_exempt_amount: Decimal
    insurance_taxable_amount: Decimal
    insurance_amount: Decimal
    cash_gross_amount: Decimal
    taxable_gross_amount: Decimal
    cash_withholding_amount: Decimal
    payment_on_account_amount: Decimal
    estimated_annual_extra_amount: Decimal
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


def _ordinary_payroll(
    salary: BaseSalaryBreakdown,
    monthly_seniority: Decimal,
    estimated_annual_extras: Decimal,
    insurance_exempt: Decimal,
    insurance_taxable: Decimal,
    contribution_group: int,
    withholding_rate: Decimal,
    occupational_risk_rate: Decimal,
    rounding: str,
) -> OrdinaryPayroll:
    with localcontext(_calculation_context(rounding)):
        for field, value in (
            ("monthly_seniority", monthly_seniority),
            ("estimated_annual_extras", estimated_annual_extras),
            ("insurance_exempt", insurance_exempt),
            ("insurance_taxable", insurance_taxable),
        ):
            if (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or not Decimal(0) <= value <= MAX_INPUT_AMOUNT
                or value != value.quantize(CENT)
            ):
                raise InvalidPayrollInput(
                    field,
                    "Indica un Decimal finito no negativo, dentro del límite monetario y sin fracciones de céntimo.",
                )
        if (
            salary.extra_payments_per_year == 0
            and estimated_annual_extras != 0
        ):
            raise InvalidPayrollInput(
                "estimated_annual_extras",
                "En doce pagas no se añade una segunda prorrata de extras.",
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
        accrual = (estimated_annual_extras / 12).quantize(CENT)
        gross = salary.ordinary_payment_amount + monthly_seniority
        insurance = insurance_exempt + insurance_taxable
        if insurance > gross:
            raise InvalidPayrollInput(
                "insurance_amount",
                "Los seguros flexibles no pueden superar el bruto que sustituyen.",
            )
        cash_gross = gross - insurance
        taxable_gross = cash_gross + insurance_taxable
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
        cash_withholding = (cash_gross * withholding_rate / 100).quantize(CENT)
        payment_on_account = (
            insurance_taxable * withholding_rate / 100
        ).quantize(CENT)
        withholding = cash_withholding + payment_on_account
        return OrdinaryPayroll(
            salary=salary,
            seniority_amount=monthly_seniority,
            gross_amount=gross,
            insurance_exempt_amount=insurance_exempt,
            insurance_taxable_amount=insurance_taxable,
            insurance_amount=insurance,
            cash_gross_amount=cash_gross,
            taxable_gross_amount=taxable_gross,
            cash_withholding_amount=cash_withholding,
            payment_on_account_amount=payment_on_account,
            estimated_annual_extra_amount=estimated_annual_extras,
            extra_payment_accrual=accrual,
            uncapped_contribution_base=uncapped,
            common_contribution_base=common,
            professional_contribution_base=professional,
            contributions=lines,
            employee_contributions=employee_total,
            employer_contributions=employer_total,
            withholding_rate=withholding_rate,
            withholding_amount=withholding,
            net_amount=cash_gross - employee_total - withholding,
            employer_cash_cost=gross + employer_total,
        )


def calculate_ordinary_payroll_2026(
    annual_base_salary: Decimal,
    payments_per_year: int,
    contribution_group: int,
    withholding_rate: Decimal,
    occupational_risk_rate: Decimal,
    rounding: str,
) -> OrdinaryPayroll:
    """Keep the base-only simulator with equal extras and constant conditions."""
    with localcontext(_calculation_context(rounding)):
        salary = base_salary_from_annual(
            annual_base_salary, payments_per_year, rounding
        )
        annual_extras = (
            salary.extra_payment_amount * salary.extra_payments_per_year
        )
        return _ordinary_payroll(
            salary,
            Decimal("0.00"),
            annual_extras,
            Decimal("0.00"),
            Decimal("0.00"),
            contribution_group,
            withholding_rate,
            occupational_risk_rate,
            rounding,
        )


def calculate_ordinary_payroll_with_seniority_2026(
    annual_base_salary: Decimal,
    payments_per_year: int,
    monthly_seniority: Decimal,
    estimated_annual_extras: Decimal,
    contribution_group: int,
    withholding_rate: Decimal,
    occupational_risk_rate: Decimal,
    rounding: str,
) -> OrdinaryPayroll:
    """Add seniority and an explicit annual estimate of extra payments.

    Annual extras / 12 is contributed, not paid in the ordinary month
    (Orden PJC/297/2026, article 1). IRPF applies to cash gross under
    RIRPF article 80, using the already determined rate. Actual extra
    payments and contribution adjustments for prior months are separate.
    """
    salary = base_salary_from_annual(
        annual_base_salary, payments_per_year, rounding
    )
    return _ordinary_payroll(
        salary,
        monthly_seniority,
        estimated_annual_extras,
        Decimal("0.00"),
        Decimal("0.00"),
        contribution_group,
        withholding_rate,
        occupational_risk_rate,
        rounding,
    )


def calculate_flexible_payroll_2026(
    annual_base_salary: Decimal,
    payments_per_year: int,
    monthly_seniority: Decimal,
    estimated_annual_extras: Decimal,
    insurance_exempt: Decimal,
    insurance_taxable: Decimal,
    contribution_group: int,
    withholding_rate: Decimal,
    occupational_risk_rate: Decimal,
    rounding: str,
) -> OrdinaryPayroll:
    """Replace cash salary with insurance; recharge taxable in-kind tax.

    The contractual salary is before flexible compensation. User-classified
    exempt/taxable premiums are monthly. Exempt insurance does not escape
    Social Security; recharged tax on taxable insurance is not grossed up.
    This does not validate exemption eligibility or annual per-person caps.
    """
    salary = base_salary_from_annual(
        annual_base_salary, payments_per_year, rounding
    )
    return _ordinary_payroll(
        salary,
        monthly_seniority,
        estimated_annual_extras,
        insurance_exempt,
        insurance_taxable,
        contribution_group,
        withholding_rate,
        occupational_risk_rate,
        rounding,
    )
