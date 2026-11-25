"""Extra-payment composition and cash payment, separate from ordinary payroll."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .base_salary import CENT, MAX_INPUT_AMOUNT, _calculation_context


class InvalidExtraPaymentInput(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


def _validate_amount(amount: Decimal, field: str) -> None:
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or not Decimal(0) <= amount <= MAX_INPUT_AMOUNT
        or amount != amount.quantize(CENT)
    ):
        raise InvalidExtraPaymentInput(
            field,
            "Indica un Decimal finito no negativo, dentro del límite monetario y sin fracciones de céntimo.",
        )


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
        _validate_amount(ordinary_base_salary, "ordinary_base_salary")
        _validate_amount(monthly_seniority, "monthly_seniority")
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


@dataclass(frozen=True, slots=True)
class ExtraPaymentCash:
    gross_amount: Decimal
    withholding_rate: Decimal
    withholding_amount: Decimal
    net_amount: Decimal
    rounding: str


def calculate_extra_payment_cash(
    gross_amount: Decimal, withholding_rate: Decimal, rounding: str
) -> ExtraPaymentCash:
    """Apply the informed payment-month rate to a cash extra.

    Social Security is accounted for in ordinary monthly proration. This
    calculation neither repeats those deductions nor pays monthly insurance
    or the fixed supplement again. It does not record an actual payment.
    """
    with localcontext(_calculation_context(rounding)):
        _validate_amount(gross_amount, "gross_amount")
        if (
            not isinstance(withholding_rate, Decimal)
            or not withholding_rate.is_finite()
            or not Decimal(0) <= withholding_rate <= Decimal(100)
            or withholding_rate != withholding_rate.quantize(CENT)
        ):
            raise InvalidExtraPaymentInput(
                "withholding_rate",
                "Indica un porcentaje Decimal entre 0 y 100, con hasta dos decimales.",
            )
        withholding = (gross_amount * withholding_rate / 100).quantize(CENT)
        return ExtraPaymentCash(
            gross_amount,
            withholding_rate,
            withholding,
            gross_amount - withholding,
            rounding,
        )
