"""Build semester accruals from the relationship's complete monthly history."""

from datetime import date
from decimal import Decimal, localcontext

from payroll_engine.base_salary import (
    InvalidBaseSalaryInput,
    _calculation_context,
    base_salary_from_annual,
    base_salary_from_monthly,
)
from payroll_engine.extra_payments import InvalidExtraPaymentInput
from payroll_engine.semester_extras import (
    ExtraAccrualMonth,
    calculate_semester_extra,
)
from payroll_engine.seniority import (
    InvalidSeniorityInput,
    calculate_monthly_seniority,
)


def _month_input(relationship, conditions, month, rounding):
    end = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    if relationship.start_date > month or (
        relationship.end_date and relationship.end_date < end
    ):
        raise InvalidExtraPaymentInput(
            "relationship",
            "Alta/baja o ausencia de relación durante parte del semestre: devengo parcial pendiente.",
        )
    covering = [
        condition
        for condition in conditions
        if condition.valid_from <= month
        and (condition.valid_until is None or condition.valid_until >= end)
    ]
    if len(covering) != 1:
        raise InvalidExtraPaymentInput(
            "conditions",
            "Falta un único periodo de condiciones que cubra todo el mes; puede haber huecos o cambios dentro del mes.",
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
        "projected": end > as_of_date,
        "as_of_date": as_of_date,
    }
