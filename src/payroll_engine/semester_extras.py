"""Accrue one extra from six complete months under the agreed composition."""

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


@dataclass(frozen=True, slots=True)
class ExtraAccrualLine:
    month: date
    base_salary: Decimal
    seniority: Decimal
    reference_amount: Decimal
    accrued_amount: Decimal


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
    """Round the sum of six monthly sixths once and expose reconciliation.

    All months must be complete and incidence-free, with one payment
    modality throughout the semester. Mixed 12/14 arrangements need a
    transition rule and are rejected rather than partially accrued.
    """
    with localcontext(_calculation_context(rounding)):
        if not isinstance(months, tuple) or len(months) != 6:
            raise InvalidExtraPaymentInput(
                "months", "Se necesitan los seis meses completos del semestre."
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
                reference.monthly_accrual,
            )
            for item, reference in zip(months, references, strict=True)
        )
        amount = (
            sum((line.reference_amount for line in lines), Decimal(0)) / 6
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
