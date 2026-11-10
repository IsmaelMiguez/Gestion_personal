"""Present the initial agreed seniority profile without claiming general coverage."""

from decimal import Decimal

from payroll_engine.seniority import (
    InvalidSeniorityInput,
    calculate_monthly_seniority,
    monthly_seniority_percentage,
)

from .payroll_report_values import value_cell

PROFILE_NOTE = (
    "Perfil inicial de bienios y topes acordado para este proyecto; no es una tabla universal de convenios. "
    "El complemento fijo no forma parte de esta base. La integración en extras, cotizaciones y neto sigue pendiente."
)


def seniority_cells(relationship, condition, salary, start, rounding):
    cells = {}
    try:
        percentage = monthly_seniority_percentage(
            relationship.seniority_date, start
        )
    except InvalidSeniorityInput as error:
        return cells, str(error)
    cells["G"] = value_cell(
        "G",
        percentage,
        "Tabla acordada: 5 % por bienio, con topes por antigüedad.",
        f"Antigüedad reconocida: {relationship.seniority_date}; mes: {start:%m/%Y}; porcentaje estable: {percentage}%.",
        PROFILE_NOTE
        + " Se muestra en porcentaje, no como fracción del Excel.",
    )
    if salary is None:
        return (
            cells,
            "Falta el sueldo base para calcular el importe de antigüedad.",
        )
    amounts = [
        getattr(condition, name) for name in condition.money_fields[1:5]
    ]
    if any(amount is None for amount in amounts):
        return (
            cells,
            "Falta informar alguno de los cuatro seguros para calcular la base de antigüedad; indica 0 si no existe.",
        )
    try:
        result = calculate_monthly_seniority(
            relationship.seniority_date,
            start,
            salary.ordinary_payment_amount,
            tuple(Decimal(amount) / 100 for amount in amounts),
            rounding,
        )
    except InvalidSeniorityInput as error:
        return cells, str(error)
    cells["P"] = value_cell(
        "P",
        result.amount,
        "(Sueldo base ordinario + cuatro seguros mensuales) × antigüedad ÷ 100",
        f"({salary.ordinary_payment_amount} + {' + '.join(str(Decimal(amount) / 100) for amount in amounts)}) × {result.percentage} ÷ 100; "
        f"base = {result.calculation_base}; años completos al inicio/fin: {result.years_at_start}/{result.years_at_end}; resultado redondeado = {result.amount}.",
        PROFILE_NOTE,
    )
    return cells, ""
