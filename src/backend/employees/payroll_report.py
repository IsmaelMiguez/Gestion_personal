"""Read-only monthly reports and explanations from the same calculated values."""

from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from unicodedata import combining, normalize

from payroll_engine.base_salary import (
    MAX_INPUT_AMOUNT,
    InvalidBaseSalaryInput,
    base_salary_from_annual,
    base_salary_from_monthly,
)
from payroll_engine.ordinary_payroll import calculate_ordinary_payroll_2026

from .payroll_columns import COLUMNS
from .payroll_report_values import result_cells, value_cell


def _text(value):
    return "".join(
        c for c in normalize("NFKD", value.lower()) if not combining(c)
    ).strip()


def _pending(code, reason):
    return {
        "code": code,
        "label": dict(COLUMNS)[code],
        "value": "Pendiente",
        "formula": "No se ha ejecutado este cálculo.",
        "operands": "",
        "note": reason,
        "available": False,
    }


def _scope_reasons(relationship, condition, start, end, year):
    reasons = []
    if year != 2026:
        reasons.append("No están implementadas las reglas de este ejercicio.")
    if relationship.start_date > start or (
        relationship.end_date and relationship.end_date < end
    ):
        reasons.append(
            "Alta o baja dentro del mes: cálculo parcial pendiente."
        )
    if condition is None:
        reasons.append(
            "No hay un único periodo de condiciones que cubra todo el mes."
        )
        return reasons
    if condition.working_time_percentage != Decimal(100):
        reasons.append(
            "La cotización a jornada parcial aún no está implementada."
        )
    if _text(condition.social_security_regime) not in (
        "general",
        "regimen general",
    ):
        reasons.append(
            "El régimen registrado no identifica el Régimen General ordinario."
        )
    if _text(condition.contract_type) not in (
        "indefinido",
        "indefinido ordinario",
    ):
        reasons.append(
            "El contrato registrado no identifica el supuesto indefinido ordinario."
        )
    if condition.contribution_group not in range(1, 8):
        reasons.append(
            "Falta grupo de cotización mensual 1–7 o el grupo no está soportado."
        )
    if condition.occupational_risk_rate is None:
        reasons.append("Falta el tipo AT/EP.")
    if condition.withholding_rate_basis_points is None:
        reasons.append("Falta el IRPF informado.")
    extras = [getattr(condition, name) for name in condition.money_fields[1:]]
    if any(value is None for value in extras):
        reasons.append(
            "Hay seguros o complementos sin informar: registra 0 si no existen."
        )
    if any(value is not None and value != 0 for value in extras):
        reasons.append(
            "El motor ordinario aún no integra seguros o complementos distintos de cero."
        )
    last_day = end - timedelta(days=1)
    years = (
        last_day.year
        - relationship.seniority_date.year
        - (
            (last_day.month, last_day.day)
            < (
                relationship.seniority_date.month,
                relationship.seniority_date.day,
            )
        )
    )
    if years >= 2:
        reasons.append(
            "Debe integrarse la antigüedad aplicable antes de calcular el total de esta nómina."
        )
    return reasons


def _salary_cells(condition, rounding):
    if (
        condition.salary_amount_cents is None
        or condition.payments_per_year is None
    ):
        return {}, None, "Faltan sueldo base o número de pagas."
    amount = Decimal(condition.salary_amount_cents) / 100
    calculator = {
        "ANNUAL": base_salary_from_annual,
        "MONTHLY": base_salary_from_monthly,
    }.get(condition.salary_period)
    if calculator is None:
        return {}, None, "Falta una unidad salarial válida."
    try:
        salary = calculator(amount, condition.payments_per_year, rounding)
    except InvalidBaseSalaryInput as error:
        return {}, None, str(error)
    cell = value_cell(
        "O",
        salary.ordinary_payment_amount,
        "Anual ÷ número de pagas, o sueldo mensual informado.",
        f"Importe registrado: {amount}; unidad: {condition.salary_period}; pagas: {condition.payments_per_year}.",
        "Sueldo correspondiente a la jornada contractual; no se multiplica otra vez por el porcentaje de jornada.",
    )
    return {"O": cell}, salary, ""


def report_row(relationship, year, month, rounding):
    with localcontext(Context(prec=28, rounding=rounding)):
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        covering = [
            condition
            for condition in relationship.conditions.all()
            if condition.valid_from <= start
            and (condition.valid_until is None or condition.valid_until >= end)
        ]
        condition = covering[0] if len(covering) == 1 else None
        reasons = _scope_reasons(relationship, condition, start, end, year)
        values = {}
        for code, value in (
            ("A", str(relationship.employee)),
            ("B", f"{month:02}/{year}"),
            ("C", start.isoformat()),
        ):
            values[code] = value_cell(
                code,
                value,
                "Dato de identificación del periodo seleccionado",
                str(value),
                "No es un importe calculado.",
            )
        if condition:
            values["F"] = value_cell(
                "F",
                condition.working_time_percentage,
                "Porcentaje contractual registrado (%)",
                str(condition.working_time_percentage),
                "El Excel usa una fracción; aquí se muestra porcentaje. No implica ausencia de incidencias.",
            )
            salary_values, salary, error = _salary_cells(condition, rounding)
            values.update(salary_values)
            if error:
                reasons.append(error)
            for code, name in zip(
                ("Q", "R", "S", "T", "U"),
                condition.money_fields[1:],
                strict=True,
            ):
                amount = getattr(condition, name)
                if amount is not None:
                    values[code] = value_cell(
                        code,
                        Decimal(amount) / 100,
                        "Importe contractual registrado en céntimos ÷ 100",
                        str(amount),
                        "Dato informado; su tratamiento retributivo y fiscal aún no se integra en el motor.",
                    )
            if not reasons:
                if salary.annual_amount > MAX_INPUT_AMOUNT:
                    reasons.append(
                        "El sueldo anualizado supera el límite de entrada del motor ordinario."
                    )
            if not reasons:
                result = calculate_ordinary_payroll_2026(
                    salary.annual_amount,
                    condition.payments_per_year,
                    condition.contribution_group,
                    Decimal(condition.withholding_rate_basis_points) / 100,
                    condition.occupational_risk_rate,
                    rounding,
                )
                values.update(result_cells(result, condition))
        pending_reason = (
            " ".join(reasons)
            or "Este concepto del Excel aún no está implementado o requiere reglas de incidencias, extras o INSS."
        )
        cells = [
            values.get(code) or _pending(code, pending_reason)
            for code, label in COLUMNS
        ]
        for cell in cells:
            cell["key"] = f"{relationship.pk}:{year}:{month}:{cell['code']}"
            cell["rounding"] = rounding
            cell["period"] = f"{month:02}/{year}"
            cell["employee"] = str(relationship.employee)
            cell["company"] = str(relationship.company)
        return {
            "company": relationship.company,
            "employee": relationship.employee,
            "relationship_id": relationship.pk,
            "period": f"{month:02}/{year}",
            "cells": cells,
            "issues": reasons,
        }
