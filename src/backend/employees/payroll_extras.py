"""Explain agreed extra-payment composition without inventing paid extras."""

from decimal import Decimal

from payroll_engine.extra_payments import (
    InvalidExtraPaymentInput,
    calculate_extra_payment_reference,
)

from .payroll_report_values import value_cell


def extra_reference_cell(condition, salary, seniority_values, rounding):
    if condition.payments_per_year == 12:
        return value_cell(
            "I",
            Decimal("0.00"),
            "12 pagas: no hay extras separadas que añadir.",
            "Número de pagas = 12; prorrata adicional = 0.00.",
            "El sueldo ya se reparte en doce pagas. No se añade una segunda prorrata ni una paga extra adicional.",
        ), ""
    seniority = seniority_values.get("P")
    if salary is None or seniority is None:
        return (
            None,
            "Falta sueldo base o antigüedad calculada para obtener la referencia de las pagas extraordinarias.",
        )
    try:
        result = calculate_extra_payment_reference(
            salary.ordinary_payment_amount,
            seniority["value"],
            condition.payments_per_year,
            rounding,
        )
    except InvalidExtraPaymentInput as error:
        return None, str(error)
    return value_cell(
        "I",
        result.monthly_accrual,
        "(Sueldo base ordinario + antigüedad mensual) × 2 ÷ 12",
        f"({salary.ordinary_payment_amount} + {seniority['value']}) × 2 ÷ 12; "
        f"referencia por extra = {result.amount_per_extra}; referencia anual de extras = {result.annual_extra_amount}; "
        f"prorrata mensual = {result.monthly_accrual}; diferencia anual de redondeo pendiente = {result.annual_accrual_rounding_difference}.",
        "Composición confirmada: solo sueldo base y antigüedad. Los seguros no se suman directamente a la extra, "
        "pero intervienen en la base de cálculo de la antigüedad según el perfil acordado. El complemento fijo queda excluido. "
        "Referencia para condiciones constantes: no es el pago efectivo de julio o diciembre ni sustituye la revisión del semestre, altas/bajas, incidencias y cambios de condiciones.",
    ), ""
