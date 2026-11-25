"""Read-only monthly reports and explanations from the same calculated values."""

from datetime import date
from decimal import Context, Decimal, localcontext

from payroll_engine.base_salary import (
    MAX_INPUT_AMOUNT,
    InvalidBaseSalaryInput,
    base_salary_from_annual,
    base_salary_from_monthly,
    prorate_monthly_salary,
    standard_month_salary_days,
)
from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_ordinary_payroll_with_insurance_deductions_2026,
)

from .payroll_columns import COLUMNS
from .payroll_extras import extra_reference_cell
from .payroll_report_values import result_cells, value_cell
from .payroll_scope import monthly_contract_issues
from .payroll_seniority import seniority_cells


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
            "Sueldo base, antigüedad, complemento fijo y devengo de extras prorrateados con mes estándar de 30 días cuando sus datos están informados. La nómina parcial completa sigue pendiente de integrar cotizaciones y descuentos de seguros."
        )
    if condition is None:
        reasons.append(
            "No hay un único periodo de condiciones que cubra todo el intervalo activo del mes."
        )
        return reasons
    reasons.extend(monthly_contract_issues(condition))
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
    return reasons


def _salary_cells(condition, salary_days, rounding):
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
        prorate_monthly_salary(
            salary.ordinary_payment_amount, salary_days, rounding
        ),
        "Sueldo base mensual ÷ 30 × días salariales del mes estándar",
        f"Importe registrado: {amount}; unidad: {condition.salary_period}; pagas: {condition.payments_per_year}; "
        f"{salary.ordinary_payment_amount} ÷ 30 × {salary_days} días.",
        "Mes estándar de 30 días también en febrero. Redondeo al final, sin redondear antes el importe diario. El fin de la relación es exclusivo. El sueldo ya corresponde a la jornada contractual.",
    )
    return {"O": cell}, salary, ""


def report_row(relationship, year, month, rounding, extra_estimate):
    with localcontext(Context(prec=28, rounding=rounding)):
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        salary_days = standard_month_salary_days(
            relationship.start_date, relationship.end_date, start
        )
        active_start = max(start, relationship.start_date)
        active_end = min(end, relationship.end_date or end)
        covering = [
            condition
            for condition in relationship.conditions.all()
            if active_start < active_end
            and condition.valid_from <= active_start
            and (
                condition.valid_until is None
                or condition.valid_until >= active_end
            )
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
            salary_values, salary, error = _salary_cells(
                condition, salary_days, rounding
            )
            values.update(salary_values)
            if error:
                reasons.append(error)
            seniority_values, seniority_error = seniority_cells(
                relationship, condition, salary, start, rounding
            )
            values.update(seniority_values)
            if salary_days < 30 and "P" in seniority_values:
                monthly_amount = seniority_values["P"]["value"]
                values["P"] = value_cell(
                    "P",
                    prorate_monthly_salary(
                        monthly_amount, salary_days, rounding
                    ),
                    "Antigüedad mensual de referencia ÷ 30 × días salariales",
                    seniority_values["P"]["operands"]
                    + f" Prorrateo: {monthly_amount} ÷ 30 × {salary_days} días.",
                    seniority_values["P"]["note"]
                    + " Se prorratea una sola vez por los días de relación; no se vuelve a aplicar la jornada contractual.",
                )
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
                    if salary_days < 30 and code != "U":
                        values[code] = _pending(
                            code,
                            "Importe mensual registrado, pendiente de determinar su descuento en el periodo parcial; no se presupone el prorrateo de la prima del seguro.",
                        )
                        continue
                    values[code] = value_cell(
                        code,
                        Decimal(amount) / 100,
                        "Importe contractual registrado en céntimos ÷ 100",
                        str(amount),
                        (
                            "Complemento dinerario mensual en doce pagos. Se suma al bruto y cotiza/tributa; no entra en extras ni en la base de antigüedad."
                            if code == "U"
                            else "Prima a cargo del trabajador que se descuenta del líquido después de SS e IRPF. La etiqueta histórica exento/sujeto no modifica la fiscalidad en este perfil."
                        ),
                    )
            if salary_days < 30 and "U" in values:
                monthly_amount = values["U"]["value"]
                values["U"] = value_cell(
                    "U",
                    prorate_monthly_salary(
                        monthly_amount, salary_days, rounding
                    ),
                    "Complemento fijo mensual ÷ 30 × días salariales",
                    f"{monthly_amount} ÷ 30 × {salary_days} días.",
                    "Complemento dinerario en doce mensualidades; no entra en antigüedad ni extras.",
                )
            if salary_days < 30 and all(
                code in values and values[code]["available"]
                for code in ("O", "P", "U")
            ):
                values["W"] = value_cell(
                    "W",
                    sum(values[code]["value"] for code in ("O", "P", "U")),
                    "Sueldo base + antigüedad + complemento fijo del periodo",
                    " + ".join(
                        str(values[code]["value"]) for code in ("O", "P", "U")
                    ),
                    "Bruto devengado conocido. Cotizaciones, IRPF y líquido del periodo parcial continúan pendientes.",
                )
            if not reasons:
                if salary.annual_amount > MAX_INPUT_AMOUNT:
                    reasons.append(
                        "El sueldo anualizado supera el límite de entrada del motor ordinario."
                    )
            estimated_extras = Decimal("0.00")
            if condition.payments_per_year == 14:
                reasons.extend(extra_estimate.get("contribution_issues", []))
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
                    result = calculate_ordinary_payroll_with_insurance_deductions_2026(
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
                        fixed_supplement=Decimal(
                            condition.fixed_supplement_cents
                        )
                        / 100,
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
                and condition.fixed_supplement_cents is not None
            ):
                gross = (
                    salary.ordinary_payment_amount
                    + seniority_values["P"]["value"]
                    + Decimal(condition.fixed_supplement_cents) / 100
                )
                values["J"] = value_cell(
                    "J",
                    gross + extra_cell["value"],
                    "Bruto de referencia de mes completo + referencia mensual de extras (I)",
                    f"{gross} + {extra_cell['value']}",
                    "Equivalente de mes completo, no un importe devengado por días. La cotización utiliza X, calculada con la estimación anual; puede diferir si cambian las condiciones.",
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
            "salary_days": salary_days,
            "cells": cells,
            "issues": reasons,
        }
