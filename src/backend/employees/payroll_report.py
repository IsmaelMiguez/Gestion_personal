"""Read-only monthly reports and explanations from the same calculated values."""

from datetime import date
from decimal import Context, Decimal, localcontext
from unicodedata import combining, normalize

from payroll_engine.base_salary import (
    MAX_INPUT_AMOUNT,
    InvalidBaseSalaryInput,
    base_salary_from_annual,
    base_salary_from_monthly,
)
from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_flexible_payroll_2026,
)

from .payroll_columns import COLUMNS
from .payroll_extras import extra_reference_cell
from .payroll_report_values import result_cells, value_cell
from .payroll_seniority import seniority_cells


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
            f"Modalidad contractual «{condition.contract_type}»: el caso soportado requiere «Indefinido» o «Indefinido ordinario». "
            "«General» identifica un régimen, no una modalidad contractual."
        )
    if condition.contribution_group not in range(1, 8):
        reasons.append(
            "Falta grupo de cotización mensual 1–7 o el grupo no está soportado."
        )
    if condition.occupational_risk_rate is None:
        reasons.append("Falta el tipo AT/EP.")
    if condition.withholding_rate_basis_points is None:
        reasons.append("Falta el IRPF informado.")
    missing = [
        str(condition._meta.get_field(name).verbose_name).removesuffix(
            " (céntimos)"
        )
        for name in condition.money_fields[1:]
        if getattr(condition, name) is None
    ]
    if missing:
        reasons.append(
            f"Campos sin informar: {', '.join(missing)}. Registra 0 solo si no existen; vacío no significa cero."
        )
    if condition.fixed_supplement_cents not in (None, 0):
        reasons.append(
            "Complemento fijo distinto de cero: falta confirmar su modalidad de pago y periodicidad."
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


def report_row(relationship, year, month, rounding, extra_estimate):
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
            seniority_values, seniority_error = seniority_cells(
                relationship, condition, salary, start, rounding
            )
            values.update(seniority_values)
            if seniority_error:
                reasons.append(seniority_error)
                for code in ("G", "P"):
                    if code not in seniority_values:
                        values[code] = _pending(code, seniority_error)
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
                        "Importe mensual informado. Los seguros sustituyen salario dinerario como retribución flexible; la parte exenta/sujeta la informa el usuario y no se valida automáticamente su límite anual.",
                    )
            if not reasons:
                if salary.annual_amount > MAX_INPUT_AMOUNT:
                    reasons.append(
                        "El sueldo anualizado supera el límite de entrada del motor ordinario."
                    )
            estimated_extras = Decimal("0.00")
            if condition.payments_per_year == 14:
                estimated_extras = extra_estimate["amount"]
                if estimated_extras is None:
                    reasons.extend(
                        "Estimación anual de extras: " + issue
                        for issue in extra_estimate["issues"]
                    )
            elif len(extra_estimate["payment_modalities"]) > 1:
                reasons.append(
                    "Cambio entre 12 y 14 pagas en el ejercicio: transición de cotización pendiente."
                )
            if not reasons:
                try:
                    result = calculate_flexible_payroll_2026(
                        salary.annual_amount,
                        condition.payments_per_year,
                        seniority_values["P"]["value"],
                        estimated_extras,
                        Decimal(
                            condition.employee_insurance_exempt_cents
                            + condition.family_insurance_exempt_cents
                        )
                        / 100,
                        Decimal(
                            condition.employee_insurance_taxable_cents
                            + condition.family_insurance_taxable_cents
                        )
                        / 100,
                        condition.contribution_group,
                        Decimal(condition.withholding_rate_basis_points) / 100,
                        condition.occupational_risk_rate,
                        rounding,
                    )
                except InvalidPayrollInput as error:
                    reasons.append(str(error))
                else:
                    values.update(result_cells(result, condition))
                    for code in ("W", "AE", "BZ", "CA", "CB", "CG"):
                        values[code]["payment_breakdown"] = result
                    if condition.payments_per_year == 14:
                        for code in ("X", "Z", "AC"):
                            values[code]["annual_extra_estimate"] = (
                                extra_estimate
                            )
            extra_cell, extra_error = extra_reference_cell(
                condition, salary, seniority_values, rounding
            )
            values["I"] = (
                extra_cell
                if extra_cell is not None
                else _pending("I", extra_error)
            )
            if (
                salary is not None
                and "P" in seniority_values
                and extra_cell is not None
                and condition.fixed_supplement_cents == 0
            ):
                gross = (
                    salary.ordinary_payment_amount
                    + seniority_values["P"]["value"]
                )
                values["J"] = value_cell(
                    "J",
                    gross + extra_cell["value"],
                    "Bruto ordinario + referencia mensual de extras (I)",
                    f"{gross} + {extra_cell['value']}",
                    "Equivalente mensual de referencia. La cotización utiliza X, calculada con la estimación anual; puede diferir si cambian las condiciones.",
                )
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
