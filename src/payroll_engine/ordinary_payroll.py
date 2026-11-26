"""Ordinary payments and period contributions for indefinite contracts.

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
class PeriodContributions:
    estimated_annual_extra_amount: Decimal
    annual_salary_days: int
    contribution_days: int
    extra_payment_accrual: Decimal
    uncapped_contribution_base: Decimal
    common_contribution_base: Decimal
    professional_contribution_base: Decimal
    minimum_common_base: Decimal
    minimum_professional_base: Decimal
    contributions: tuple[Contribution, ...]
    employee_contributions: Decimal
    employer_contributions: Decimal


@dataclass(frozen=True, slots=True)
class OrdinaryPayroll:
    salary: BaseSalaryBreakdown
    seniority_amount: Decimal
    fixed_supplement_amount: Decimal
    gross_amount: Decimal
    insurance_exempt_amount: Decimal
    insurance_taxable_amount: Decimal
    insurance_amount: Decimal
    cash_gross_amount: Decimal
    taxable_gross_amount: Decimal
    cash_withholding_amount: Decimal
    net_before_insurance: Decimal
    estimated_annual_extra_amount: Decimal
    annual_salary_days: int
    contribution_days: int
    extra_payment_accrual: Decimal
    uncapped_contribution_base: Decimal
    common_contribution_base: Decimal
    professional_contribution_base: Decimal
    minimum_common_base: Decimal
    minimum_professional_base: Decimal
    contributions: tuple[Contribution, ...]
    employee_contributions: Decimal
    employer_contributions: Decimal
    withholding_rate: Decimal
    withholding_amount: Decimal
    net_amount: Decimal
    employer_cash_cost: Decimal


def _validate_money_amount(value, field):
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or not 0 <= value <= MAX_INPUT_AMOUNT
        or value != value.quantize(CENT)
    ):
        raise InvalidPayrollInput(
            field,
            "Indica un Decimal monetario finito, no negativo y sin fracciones de céntimo dentro del límite admitido.",
        )


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
    contribution_days: int,
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
        lower = (lower * contribution_days / 30).quantize(CENT)
        upper = (
            (upper * contribution_days / 30).quantize(CENT)
            if upper.is_finite()
            else upper
        )
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
    fixed_supplement: Decimal,
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
            ("fixed_supplement", fixed_supplement),
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
        gross = (
            salary.ordinary_payment_amount
            + monthly_seniority
            + fixed_supplement
        )
        insurance = insurance_exempt + insurance_taxable
        cash_gross = gross
        taxable_gross = gross
        period = calculate_period_contributions_2026(
            gross,
            estimated_annual_extras,
            360,
            30,
            contribution_group,
            occupational_risk_rate,
            rounding,
        )
        common = period.common_contribution_base
        professional = period.professional_contribution_base
        lines = period.contributions
        employee_total = period.employee_contributions
        employer_total = period.employer_contributions
        cash_withholding = (cash_gross * withholding_rate / 100).quantize(CENT)
        withholding = cash_withholding
        net_before_insurance = gross - employee_total - withholding
        return OrdinaryPayroll(
            salary=salary,
            seniority_amount=monthly_seniority,
            fixed_supplement_amount=fixed_supplement,
            gross_amount=gross,
            insurance_exempt_amount=insurance_exempt,
            insurance_taxable_amount=insurance_taxable,
            insurance_amount=insurance,
            cash_gross_amount=cash_gross,
            taxable_gross_amount=taxable_gross,
            cash_withholding_amount=cash_withholding,
            net_before_insurance=net_before_insurance,
            estimated_annual_extra_amount=estimated_annual_extras,
            annual_salary_days=360,
            contribution_days=30,
            extra_payment_accrual=period.extra_payment_accrual,
            uncapped_contribution_base=period.uncapped_contribution_base,
            common_contribution_base=common,
            professional_contribution_base=professional,
            minimum_common_base=period.minimum_common_base,
            minimum_professional_base=period.minimum_professional_base,
            contributions=lines,
            employee_contributions=employee_total,
            employer_contributions=employer_total,
            withholding_rate=withholding_rate,
            withholding_amount=withholding,
            net_amount=net_before_insurance - insurance,
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
        Decimal("0.00"),
        contribution_group,
        withholding_rate,
        occupational_risk_rate,
        rounding,
    )


def calculate_ordinary_payroll_with_insurance_deductions_2026(
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
    fixed_supplement: Decimal,
) -> OrdinaryPayroll:
    """Calculate payroll first, then deduct employee-paid insurance from net.

    Legacy exempt/taxable fields only identify the recorded premiums in this
    profile. They neither reduce taxable salary nor create in-kind income.
    A negative transfer is retained explicitly instead of hiding a shortfall.
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
        fixed_supplement,
        contribution_group,
        withholding_rate,
        occupational_risk_rate,
        rounding,
    )


def _validate_contribution_inputs(
    gross_amount,
    estimated_annual_extras,
    annual_salary_days,
    contribution_days,
    contribution_group,
    occupational_risk_rate,
):
    for field, value in (
        ("gross_amount", gross_amount),
        ("estimated_annual_extras", estimated_annual_extras),
    ):
        _validate_money_amount(value, field)
    for field, value, maximum in (
        ("annual_salary_days", annual_salary_days, 360),
        ("contribution_days", contribution_days, 30),
        ("contribution_group", contribution_group, 7),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise InvalidPayrollInput(
                field, f"Indica un entero entre 1 y {maximum}."
            )
    _validate_rate(occupational_risk_rate, "occupational_risk_rate")


def _period_contributions(
    gross_amount,
    estimated_annual_extras,
    annual_salary_days,
    contribution_days,
    minimum,
    professional_minimum,
    occupational_risk_rate,
):
    accrual = (
        estimated_annual_extras / annual_salary_days * contribution_days
    ).quantize(CENT)
    uncapped = gross_amount + accrual
    maximum = (rules.MAXIMUM_BASE * contribution_days / 30).quantize(CENT)
    common = min(maximum, max(minimum, uncapped))
    professional = min(maximum, max(professional_minimum, uncapped))
    lines = _contributions(
        common,
        professional,
        uncapped,
        occupational_risk_rate,
        contribution_days,
    )
    return PeriodContributions(
        estimated_annual_extras,
        annual_salary_days,
        contribution_days,
        accrual,
        uncapped,
        common,
        professional,
        minimum,
        professional_minimum,
        lines,
        sum((line.employee_amount for line in lines), Decimal("0.00")),
        sum((line.employer_amount for line in lines), Decimal("0.00")),
    )


def calculate_period_contributions_2026(
    gross_amount: Decimal,
    estimated_annual_extras: Decimal,
    annual_salary_days: int,
    contribution_days: int,
    contribution_group: int,
    occupational_risk_rate: Decimal,
    rounding: str,
) -> PeriodContributions:
    """Contribute full-time period earnings and normalize the extra estimate."""
    with localcontext(_calculation_context(rounding)):
        _validate_contribution_inputs(
            gross_amount,
            estimated_annual_extras,
            annual_salary_days,
            contribution_days,
            contribution_group,
            occupational_risk_rate,
        )
        minimum = (
            rules.MONTHLY_MINIMUM_BASES[contribution_group - 1]
            * contribution_days
            / 30
        ).quantize(CENT)
        professional_minimum = (
            rules.MINIMUM_PROFESSIONAL_BASE * contribution_days / 30
        ).quantize(CENT)
        return _period_contributions(
            gross_amount,
            estimated_annual_extras,
            annual_salary_days,
            contribution_days,
            minimum,
            professional_minimum,
            occupational_risk_rate,
        )


def calculate_part_time_contributions_2026(
    gross_amount: Decimal,
    estimated_annual_extras: Decimal,
    annual_salary_days: int,
    contribution_days: int,
    contribution_group: int,
    occupational_risk_rate: Decimal,
    worked_hours: Decimal,
    rounding: str,
) -> PeriodContributions:
    """Apply actual-hour minima, without reducing salary or maximum by FTE.

    Orden PJC/297/2026, articles 38–39. Ordinary indefinite contracts,
    monthly groups 1–7, without incidents or additional/overtime hours.
    """
    with localcontext(_calculation_context(rounding)):
        _validate_contribution_inputs(
            gross_amount,
            estimated_annual_extras,
            annual_salary_days,
            contribution_days,
            contribution_group,
            occupational_risk_rate,
        )
        if (
            not isinstance(worked_hours, Decimal)
            or not worked_hours.is_finite()
            or not 0 < worked_hours <= 744
            or worked_hours != worked_hours.quantize(CENT)
        ):
            raise InvalidPayrollInput(
                "worked_hours",
                "Introduce las horas ordinarias realmente trabajadas en este mes (Decimal mayor que 0, hasta 744 y con dos decimales como máximo).",
            )
        minimum = (
            rules.HOURLY_MINIMUM_BASES[contribution_group - 1] * worked_hours
        ).quantize(CENT)
        professional_minimum = (
            rules.MINIMUM_PROFESSIONAL_HOURLY_BASE * worked_hours
        ).quantize(CENT)
        return _period_contributions(
            gross_amount,
            estimated_annual_extras,
            annual_salary_days,
            contribution_days,
            minimum,
            professional_minimum,
            occupational_risk_rate,
        )


def calculate_condition_change_contributions_2026(
    segments: tuple[tuple[Decimal, int], ...],
    estimated_annual_extras: Decimal,
    annual_salary_days: int,
    contribution_group: int,
    occupational_risk_rate: Decimal,
    rounding: str,
) -> PeriodContributions:
    """Enforce each full-time segment's floor, with one monthly maximum.

    Same contribution group and risk rate throughout, without incidents.
    Solidarity still uses actual uncapped remuneration, not minimum uplift.
    """
    with localcontext(_calculation_context(rounding)):
        if not isinstance(segments, tuple) or len(segments) < 2:
            raise InvalidPayrollInput(
                "segments",
                "Indica al menos dos tramos de devengo y días cotizados.",
            )
        for index, segment in enumerate(segments):
            if not isinstance(segment, tuple) or len(segment) != 2:
                raise InvalidPayrollInput(
                    "segments",
                    "Cada tramo debe contener importe y días cotizados.",
                )
            gross, days = segment
            if type(days) is not int or not 0 <= days <= 30:
                raise InvalidPayrollInput(
                    "segments", "Días cotizados de tramo inválidos."
                )
            _validate_money_amount(gross, f"segments[{index}].gross_amount")
            if days == 0 and gross != 0:
                raise InvalidPayrollInput(
                    "segments",
                    "Un tramo con cero días cotizados no puede tener bruto devengado.",
                )
        gross = sum((amount for amount, days in segments), Decimal(0))
        days = sum(days for amount, days in segments)
        _validate_contribution_inputs(
            gross,
            estimated_annual_extras,
            annual_salary_days,
            days,
            contribution_group,
            occupational_risk_rate,
        )
        extra_rate = estimated_annual_extras / annual_salary_days
        minimum = sum(
            max(
                rules.MONTHLY_MINIMUM_BASES[contribution_group - 1]
                * count
                / 30,
                amount + extra_rate * count,
            )
            for amount, count in segments
        ).quantize(CENT)
        professional_minimum = sum(
            max(
                rules.MINIMUM_PROFESSIONAL_BASE * count / 30,
                amount + extra_rate * count,
            )
            for amount, count in segments
        ).quantize(CENT)
        return _period_contributions(
            gross,
            estimated_annual_extras,
            annual_salary_days,
            days,
            minimum,
            professional_minimum,
            occupational_risk_rate,
        )
