"""Accrue one extra from six months, weighted by salary days under the agreed composition."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from .base_salary import CENT, _calculation_context
from .extra_payments import (
    InvalidExtraPaymentInput,
    calculate_extra_payment_reference,
)


@dataclass(frozen=True, slots=True)
class ExtraAccrualMonth:
    month: date
    base_salary: Decimal
    seniority: Decimal
    payments_per_year: int
    salary_days: int


@dataclass(frozen=True, slots=True)
class ExtraAccrualLine:
    month: date
    base_salary: Decimal
    seniority: Decimal
    reference_amount: Decimal
    accrued_amount: Decimal
    salary_days: int


@dataclass(frozen=True, slots=True)
class SemesterExtra:
    payment_month: date
    lines: tuple[ExtraAccrualLine, ...]
    payments_per_year: int
    amount: Decimal
    rounded_months_total: Decimal
    rounding_difference: Decimal
    rounding: str


def calculate_semester_extra(
    months: tuple[ExtraAccrualMonth, ...], rounding: str
) -> SemesterExtra:
    """Round the sum of monthly references × salary days / 180 once.

    All six months must be supplied, including zero-day months outside the
    employment relationship, with one payment
    modality throughout the semester. Mixed 12/14 arrangements need a
    transition rule and are rejected rather than partially accrued.
    """
    with localcontext(_calculation_context(rounding)):
        if not isinstance(months, tuple) or len(months) != 6:
            raise InvalidExtraPaymentInput(
                "months",
                "Se necesitan los seis meses del semestre, incluidos los que no tengan días de relación laboral.",
            )
        for item in months:
            if (
                not isinstance(item, ExtraAccrualMonth)
                or type(item.month) is not date
            ):
                raise InvalidExtraPaymentInput(
                    "months",
                    "Cada mes debe incluir una fecha sin componente horario.",
                )
        first = months[0].month
        if first.day != 1 or first.month not in (1, 7):
            raise InvalidExtraPaymentInput(
                "months",
                "El semestre debe comenzar el 1 de enero o el 1 de julio.",
            )
        expected = tuple(
            date(first.year, first.month + index, 1) for index in range(6)
        )
        if tuple(item.month for item in months) != expected:
            raise InvalidExtraPaymentInput(
                "months",
                "Los meses deben ser consecutivos, únicos y estar ordenados dentro del mismo semestre.",
            )
        references = []
        for index, item in enumerate(months):
            if (
                type(item.salary_days) is not int
                or not 0 <= item.salary_days <= 30
            ):
                raise InvalidExtraPaymentInput(
                    f"months[{index}].salary_days",
                    "Indica días salariales entre 0 y 30.",
                )
            try:
                reference = calculate_extra_payment_reference(
                    item.base_salary,
                    item.seniority,
                    item.payments_per_year,
                    rounding,
                )
            except InvalidExtraPaymentInput as error:
                raise InvalidExtraPaymentInput(
                    f"months[{index}].{error.field}", str(error)
                ) from error
            if item.salary_days == 0 and (
                item.base_salary != 0 or item.seniority != 0
            ):
                raise InvalidExtraPaymentInput(
                    f"months[{index}].salary_days",
                    "Un mes sin relación laboral debe tener base y antigüedad cero.",
                )
            references.append(reference)
        if len({item.payments_per_year for item in months}) != 1:
            raise InvalidExtraPaymentInput(
                "payments_per_year",
                "Cambio entre 12 y 14 pagas dentro del semestre: falta definir su transición.",
            )
        lines = tuple(
            ExtraAccrualLine(
                item.month,
                item.base_salary,
                item.seniority,
                reference.amount_per_extra,
                (reference.amount_per_extra * item.salary_days / 180).quantize(
                    CENT
                ),
                item.salary_days,
            )
            for item, reference in zip(months, references, strict=True)
        )
        amount = (
            sum(
                (line.reference_amount * line.salary_days for line in lines),
                Decimal(0),
            )
            / 180
        ).quantize(CENT)
        monthly_total = sum(
            (line.accrued_amount for line in lines), Decimal("0.00")
        )
        return SemesterExtra(
            date(first.year, 7 if first.month == 1 else 12, 1),
            lines,
            months[0].payments_per_year,
            amount,
            monthly_total,
            amount - monthly_total,
            rounding,
        )
