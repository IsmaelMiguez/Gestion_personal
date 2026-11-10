"""Initial seniority schedule agreed for this project, not a universal rule."""

from calendar import isleap, monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from .base_salary import CENT, MAX_INPUT_AMOUNT, _calculation_context


class InvalidSeniorityInput(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


class UnresolvedSeniorityPeriod(InvalidSeniorityInput):
    """The period needs an effective-date policy that is not agreed yet."""


@dataclass(frozen=True, slots=True)
class MonthlySeniority:
    years_at_start: int
    years_at_end: int
    percentage: Decimal
    calculation_base: Decimal
    amount: Decimal
    rounding: str


def _percentage(years: int) -> Decimal:
    if years < 6:
        cap = 10
    elif years < 15:
        cap = 25
    elif years < 20:
        cap = 40
    else:
        cap = 60
    return Decimal(min((years // 2) * 5, cap))


def _completed_years(recognized_date: date, reference: date) -> int:
    return (
        reference.year
        - recognized_date.year
        - (
            (reference.month, reference.day)
            < (recognized_date.month, recognized_date.day)
        )
    )


def monthly_seniority_percentage(
    recognized_date: date, month_start: date
) -> Decimal:
    """Return a stable monthly rate; leave effective-date decisions explicit."""
    for name, value in (
        ("recognized_date", recognized_date),
        ("month_start", month_start),
    ):
        if type(value) is not date:
            raise InvalidSeniorityInput(
                name, "Indica una fecha sin componente horario."
            )
    if month_start.day != 1:
        raise InvalidSeniorityInput(
            "month_start", "El periodo debe comenzar el día 1 del mes."
        )
    if recognized_date > month_start:
        raise InvalidSeniorityInput(
            "recognized_date",
            "La antigüedad reconocida es posterior al inicio del mes.",
        )
    month_end = date(
        month_start.year,
        month_start.month,
        monthrange(month_start.year, month_start.month)[1],
    )
    first_years = _completed_years(recognized_date, month_start)
    last_years = _completed_years(recognized_date, month_end)
    if (
        (recognized_date.month, recognized_date.day) == (2, 29)
        and not isleap(month_start.year)
        and month_start.month == 2
    ):
        if _percentage(last_years) != _percentage(last_years + 1):
            raise UnresolvedSeniorityPeriod(
                "recognized_date",
                "Antigüedad del 29 de febrero: falta acordar el aniversario en años no bisiestos.",
            )
    if _percentage(first_years) != _percentage(last_years):
        raise UnresolvedSeniorityPeriod(
            "month_start",
            "Cambio de tramo de antigüedad dentro del mes: falta acordar la fecha de efectos.",
        )
    return _percentage(first_years)


def calculate_monthly_seniority(
    recognized_date: date,
    month_start: date,
    ordinary_base_salary: Decimal,
    insurance_amounts: tuple[Decimal, Decimal, Decimal, Decimal],
    rounding: str,
) -> MonthlySeniority:
    """Apply the agreed percentage to base salary plus the four insurances."""
    with localcontext(_calculation_context(rounding)):
        percentage = monthly_seniority_percentage(recognized_date, month_start)
        if (
            not isinstance(insurance_amounts, tuple)
            or len(insurance_amounts) != 4
        ):
            raise InvalidSeniorityInput(
                "insurance_amounts",
                "Indica explícitamente los cuatro seguros, con 0 si no existen.",
            )
        for name, amount in (
            ("ordinary_base_salary", ordinary_base_salary),
            *(
                (f"insurance_amounts[{index}]", value)
                for index, value in enumerate(insurance_amounts)
            ),
        ):
            if (
                not isinstance(amount, Decimal)
                or not amount.is_finite()
                or not Decimal(0) <= amount <= MAX_INPUT_AMOUNT
                or amount != amount.quantize(CENT)
            ):
                raise InvalidSeniorityInput(
                    name,
                    "Indica un Decimal finito no negativo, dentro del límite monetario y sin fracciones de céntimo.",
                )
        base = ordinary_base_salary + sum(insurance_amounts, Decimal("0.00"))
        last_day = date(
            month_start.year,
            month_start.month,
            monthrange(month_start.year, month_start.month)[1],
        )
        return MonthlySeniority(
            _completed_years(recognized_date, month_start),
            _completed_years(recognized_date, last_day),
            percentage,
            base,
            (base * percentage / 100).quantize(CENT),
            rounding,
        )
