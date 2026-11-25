"""Build semester accruals from the relationship's monthly history and standard salary days."""

from datetime import date
from decimal import Decimal, localcontext

from payroll_engine.base_salary import (
    InvalidBaseSalaryInput,
    _calculation_context,
    base_salary_from_annual,
    base_salary_from_monthly,
    standard_month_salary_days,
)
from payroll_engine.extra_payments import (
    InvalidExtraPaymentInput,
    calculate_extra_payment_cash,
)
from payroll_engine.semester_extras import (
    ExtraAccrualMonth,
    calculate_semester_extra,
)
from payroll_engine.seniority import (
    InvalidSeniorityInput,
    calculate_monthly_seniority,
)

from .payroll_scope import monthly_contract_issues


def _payment_cash(relationship, conditions, result, rounding):
    start = result.payment_month
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    if start.year != 2026:
        return (
            None,
            "El pago fuera de 2026 queda pendiente de verificar su alcance.",
        )
    if relationship.start_date > start or (
        relationship.end_date and relationship.end_date < end
    ):
        return (
            None,
            "No hay relación laboral durante todo el mes de pago: liquidación o pago tras baja pendiente.",
        )
    covering = [
        condition
        for condition in conditions
        if condition.valid_from <= start
        and (condition.valid_until is None or condition.valid_until >= end)
    ]
    if len(covering) != 1:
        return (
            None,
            "No hay condiciones únicas para todo el mes de pago. Falta concretar la fecha efectiva de pago y el IRPF aplicable.",
        )
    condition = covering[0]
    issues = monthly_contract_issues(condition)
    if condition.payments_per_year != 14:
        issues.append(
            "La modalidad del mes de pago no es de catorce pagas: transición pendiente."
        )
    if condition.withholding_rate_basis_points is None:
        issues.append(
            "Falta el porcentaje IRPF informado para el mes de pago."
        )
    if issues:
        return None, " ".join(issues)
    try:
        with localcontext(_calculation_context(rounding)):
            payment = calculate_extra_payment_cash(
                result.amount,
                Decimal(condition.withholding_rate_basis_points) / 100,
                rounding,
            )
    except InvalidExtraPaymentInput as error:
        return None, str(error)
    return payment, ""


def _month_input(relationship, conditions, month, rounding):
    end = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    salary_days = standard_month_salary_days(
        relationship.start_date, relationship.end_date, month
    )
    if salary_days == 0:
        modalities = {condition.payments_per_year for condition in conditions}
        if len(modalities) != 1 or not modalities <= {12, 14}:
            raise InvalidExtraPaymentInput(
                "payments_per_year",
                "No hay una modalidad única de 12 o 14 pagas para identificar los meses sin relación laboral.",
            )
        return ExtraAccrualMonth(
            month, Decimal(0), Decimal(0), modalities.pop(), 0
        )
    active_start = max(month, relationship.start_date)
    active_end = min(end, relationship.end_date or end)
    covering = [
        condition
        for condition in conditions
        if condition.valid_from <= active_start
        and (
            condition.valid_until is None
            or condition.valid_until >= active_end
        )
    ]
    if len(covering) != 1:
        raise InvalidExtraPaymentInput(
            "conditions",
            "Falta un único periodo de condiciones que cubra todo el intervalo activo del mes; puede haber huecos o cambios dentro del mes.",
        )
    condition = covering[0]
    calculator = {
        "ANNUAL": base_salary_from_annual,
        "MONTHLY": base_salary_from_monthly,
    }.get(condition.salary_period)
    if calculator is None or condition.salary_amount_cents is None:
        raise InvalidExtraPaymentInput(
            "salary", "Faltan sueldo base y unidad salarial válidos."
        )
    with localcontext(_calculation_context(rounding)):
        salary = calculator(
            Decimal(condition.salary_amount_cents) / 100,
            condition.payments_per_year,
            rounding,
        )
    insurances = [
        getattr(condition, name) for name in condition.money_fields[1:5]
    ]
    if any(amount is None for amount in insurances):
        raise InvalidExtraPaymentInput(
            "insurances",
            "Falta informar alguno de los cuatro seguros para calcular la antigüedad; indica 0 si no existe.",
        )
    with localcontext(_calculation_context(rounding)):
        seniority = calculate_monthly_seniority(
            relationship.seniority_date,
            month,
            salary.ordinary_payment_amount,
            tuple(Decimal(amount) / 100 for amount in insurances),
            rounding,
        )
    return ExtraAccrualMonth(
        month,
        salary.ordinary_payment_amount,
        seniority.amount,
        condition.payments_per_year,
        salary_days,
    )


def semester_extra(relationship, year, first_month, rounding, as_of_date):
    conditions = list(relationship.conditions.all())
    rows = []
    inputs = []
    issues = []
    for number in range(first_month, first_month + 6):
        month = date(year, number, 1)
        try:
            item = _month_input(relationship, conditions, month, rounding)
        except (
            InvalidExtraPaymentInput,
            InvalidBaseSalaryInput,
            InvalidSeniorityInput,
        ) as error:
            reason = str(error)
            issues.append(f"{month:%m/%Y}: {reason}")
            rows.append({"month": month, "issue": reason})
        else:
            inputs.append(item)
            rows.append(
                {
                    "month": month,
                    "base_salary": item.base_salary,
                    "seniority": item.seniority,
                    "payments": item.payments_per_year,
                    "salary_days": item.salary_days,
                }
            )
    result = None
    if not issues:
        try:
            result = calculate_semester_extra(tuple(inputs), rounding)
        except InvalidExtraPaymentInput as error:
            issues.append(str(error))
        else:
            for row, line in zip(rows, result.lines, strict=True):
                row["reference"] = line.reference_amount
                row["accrued"] = line.accrued_amount
    end = date(year, 7, 1) if first_month == 1 else date(year + 1, 1, 1)
    payment = None
    payment_issue = ""
    if result is not None and result.payments_per_year == 14:
        payment, payment_issue = _payment_cash(
            relationship, conditions, result, rounding
        )
    return {
        "company": relationship.company,
        "employee": relationship.employee,
        "relationship_id": relationship.pk,
        "year": year,
        "semester": 1 if first_month == 1 else 2,
        "payment_label": "Julio" if first_month == 1 else "Diciembre",
        "rows": rows,
        "issues": issues,
        "result": result,
        "payment": payment,
        "payment_issue": payment_issue,
        "projected": end > as_of_date,
        "as_of_date": as_of_date,
    }


def annual_extra_estimate(relationship, year, rounding, as_of_date):
    """Estimate both extras from recorded history, retaining missing-data reasons."""
    semesters = [
        semester_extra(relationship, year, first, rounding, as_of_date)
        for first in (1, 7)
    ]
    issues = [issue for semester in semesters for issue in semester["issues"]]
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)
    modalities = {
        condition.payments_per_year
        for condition in relationship.conditions.all()
        if condition.valid_from < year_end
        and (
            condition.valid_until is None or condition.valid_until > year_start
        )
        and condition.payments_per_year is not None
    }
    if len(modalities) > 1:
        issues.append(
            "Cambio entre 12 y 14 pagas durante el ejercicio: falta definir la transición para la cotización."
        )
    amount = None
    if not issues:
        with localcontext(_calculation_context(rounding)):
            amount = sum(
                (semester["result"].amount for semester in semesters),
                Decimal("0.00"),
            )
    salary_days = (
        sum(
            row["salary_days"]
            for semester in semesters
            for row in semester["rows"]
        )
        if not issues
        else None
    )
    return {
        "annual_salary_days": salary_days,
        "amount": amount,
        "semesters": semesters,
        "issues": issues,
        "payment_modalities": modalities,
    }
