"""Extra-payment references for constant conditions, before semester accrual."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .base_salary import CENT, MAX_INPUT_AMOUNT, _calculation_context


class InvalidExtraPaymentInput(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ExtraPaymentReference:
    separate_payments_per_year: int
    amount_per_extra: Decimal
    annual_extra_amount: Decimal
    monthly_accrual: Decimal
    annual_accrual_rounding_difference: Decimal
    rounding: str


def calculate_extra_payment_reference(
    ordinary_base_salary: Decimal,
    monthly_seniority: Decimal,
    payments_per_year: int,
    rounding: str,
) -> ExtraPaymentReference:
    """Include only base salary and the already calculated seniority amount.

    For 12 payments those concepts are already distributed in ordinary pay;
    no extra payment is added. For 14, this is an equal-extra reference,
    not an actual July/December payment or a historical accrual calculation.
    """
    with localcontext(_calculation_context(rounding)):
        if type(payments_per_year) is not int or payments_per_year not in (
            12,
            14,
        ):
            raise InvalidExtraPaymentInput(
                "payments_per_year", "Indica 12 o 14 pagas como número entero."
            )
        for name, amount in (
            ("ordinary_base_salary", ordinary_base_salary),
            ("monthly_seniority", monthly_seniority),
        ):
            if (
                not isinstance(amount, Decimal)
                or not amount.is_finite()
                or not Decimal(0) <= amount <= MAX_INPUT_AMOUNT
                or amount != amount.quantize(CENT)
            ):
                raise InvalidExtraPaymentInput(
                    name,
                    "Indica un Decimal finito no negativo, dentro del límite monetario y sin fracciones de céntimo.",
                )
        count = payments_per_year - 12
        amount = (
            ordinary_base_salary + monthly_seniority
            if count
            else Decimal("0.00")
        )
        annual = amount * count
        monthly = (annual / 12).quantize(CENT)
        return ExtraPaymentReference(
            count,
            amount,
            annual,
            monthly,
            annual - monthly * 12,
            rounding,
        )
