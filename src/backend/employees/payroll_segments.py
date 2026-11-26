"""Monthly earnings across condition changes, with one contribution calculation."""

from decimal import Decimal, localcontext

from payroll_engine.base_salary import (
    CENT,
    InvalidBaseSalaryInput,
    _calculation_context,
    base_salary_from_annual,
    base_salary_from_monthly,
    monthly_contribution_days,
    prorate_monthly_salary,
    standard_month_salary_days,
)
from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_condition_change_contributions_2026,
)

from .payroll_report_values import (
    contribution_cells,
    report_result,
    value_cell,
)
from .payroll_scope import condition_segments, monthly_contract_issues
from .payroll_seniority import seniority_cells


def _segment_earnings(relationship, start, segment, rounding):
    condition = segment["condition"]
    days = segment["salary_days"]
    cells = {}
    issues = []
    salary = None
    calculator = {
        "ANNUAL": base_salary_from_annual,
        "MONTHLY": base_salary_from_monthly,
    }.get(condition.salary_period)
    if (
        calculator is None
        or condition.salary_amount_cents is None
        or condition.payments_per_year is None
    ):
        issues.append("Faltan sueldo base, unidad salarial o pagas.")
    else:
        try:
            salary = calculator(
                Decimal(condition.salary_amount_cents) / 100,
                condition.payments_per_year,
                rounding,
            )
        except InvalidBaseSalaryInput as error:
            issues.append(str(error))
        else:
            cells["O"] = prorate_monthly_salary(
                salary.ordinary_payment_amount, days, rounding
            )
    seniority, error = seniority_cells(
        relationship, condition, salary, start, rounding
    )
    if error:
        issues.append(error)
    if "P" in seniority:
        cells["P"] = prorate_monthly_salary(
            seniority["P"]["value"], days, rounding
        )
    for code, name in zip(
        ("Q", "R", "S", "T", "U"), condition.money_fields[1:], strict=True
    ):
        amount = getattr(condition, name)
        if amount is None:
            issues.append(
                f"Falta {condition._meta.get_field(name).verbose_name}."
            )
        else:
            cells[code] = prorate_monthly_salary(
                Decimal(amount) / 100, days, rounding
            )
    if all(code in cells for code in ("O", "P", "U")):
        cells["W"] = sum(cells[code] for code in ("O", "P", "U"))
    if condition.withholding_rate_basis_points is None:
        issues.append("Falta el IRPF informado para este tramo.")
    segment.update(
        values=cells,
        salary=salary,
        seniority=seniority,
        issues=issues,
        withholding_rate=Decimal(condition.withholding_rate_basis_points) / 100
        if condition.withholding_rate_basis_points is not None
        else None,
    )
    return segment


def _segmented_values(relationship, start, segments, salary_days, rounding):
    values = {}
    issues = []
    for segment in segments:
        try:
            _segment_earnings(relationship, start, segment, rounding)
        except InvalidBaseSalaryInput as error:
            segment.update(
                values={}, salary=None, seniority={}, issues=[str(error)]
            )
        issues.extend(
            f"{segment['start']:%d/%m}–{segment['last_day']:%d/%m}: {issue}"
            for issue in segment["issues"]
        )
    for code in ("O", "P", "Q", "R", "S", "T", "U", "W"):
        if all(code in segment["values"] for segment in segments):
            amounts = [segment["values"][code] for segment in segments]
            values[code] = value_cell(
                code,
                sum(amounts),
                "Suma de importes calculados en cada tramo de condiciones",
                " + ".join(map(str, amounts)),
                "Cada concepto/tramo se redondea una vez. Los seguros se descuentan del líquido; no se añaden al bruto. Consulta el desglose por fechas.",
            )
    if "W" in values:
        for code in ("AE", "CF"):
            values[code] = value_cell(
                code,
                values["W"]["value"],
                "Bruto devengado del mes sin prestación INSS",
                str(values["W"]["value"]),
                "Los seguros no reducen la base IRPF.",
            )
    rates = {
        segment["condition"].withholding_rate_basis_points
        for segment in segments
    }
    if (
        len(rates) == 1
        and None not in rates
        and "W" in values
        and start.year == 2026
    ):
        rate = Decimal(next(iter(rates))) / 100
        tax = (values["W"]["value"] * rate / 100).quantize(CENT)
        values["BZ"] = value_cell(
            "BZ",
            tax,
            "Bruto mensual × tipo IRPF informado común ÷ 100",
            f"{values['W']['value']} × {rate} ÷ 100",
            "Retención redondeada una sola vez sobre el pago mensual; no se regulariza el tipo.",
        )
    elif len(rates) > 1:
        issues.append(
            "Cambia el tipo IRPF informado dentro del mes: falta confirmar la fecha de pago y el tipo aplicable; no se reparte la retención automáticamente por fechas de devengo."
        )
    if all("G" in segment["seniority"] for segment in segments):
        values["G"] = dict(segments[0]["seniority"]["G"])
    percentage = (
        sum(
            segment["condition"].working_time_percentage
            * segment["salary_days"]
            for segment in segments
        )
        / salary_days
    )
    values["F"] = value_cell(
        "F",
        percentage.quantize(CENT),
        "Media de jornada contractual ponderada por días salariales",
        str(percentage),
        "Referencia equivalente; no se usa para volver a reducir el sueldo.",
    )
    modes = {segment["condition"].payments_per_year for segment in segments}
    references_known = all(
        segment["salary"] is not None and "P" in segment["seniority"]
        for segment in segments
    )
    if modes == {12}:
        values["I"] = value_cell(
            "I",
            Decimal("0.00"),
            "Doce pagas: no se añade otra extra separada",
            "0",
            "No duplica conceptos ya distribuidos en las pagas ordinarias.",
        )
    elif modes == {14} and references_known:
        reference = (
            sum(
                (
                    segment["salary"].ordinary_payment_amount
                    + segment["seniority"]["P"]["value"]
                )
                * segment["salary_days"]
                for segment in segments
            )
            / salary_days
            / 6
        )
        values["I"] = value_cell(
            "I",
            reference.quantize(CENT),
            "Media de base + antigüedad por días salariales ÷ 6",
            str(reference),
            "Referencia equivalente de mes completo; no es el abono de la extra ni la prorrata cotizable X.",
        )
    if (
        references_known
        and "I" in values
        and all(
            segment["condition"].fixed_supplement_cents is not None
            for segment in segments
        )
    ):
        reference = (
            sum(
                (
                    segment["salary"].ordinary_payment_amount
                    + segment["seniority"]["P"]["value"]
                    + Decimal(segment["condition"].fixed_supplement_cents)
                    / 100
                )
                * segment["salary_days"]
                for segment in segments
            )
            / salary_days
        )
        values["J"] = value_cell(
            "J",
            (reference + values["I"]["value"]).quantize(CENT),
            "Bruto mensual equivalente ponderado + referencia I",
            f"{reference} + {values['I']['value']}",
            "Referencia de mes completo, no devengo adicional.",
        )
    return values, issues


def segmented_report_row(
    relationship, start, rounding, extra_estimate, worked_hours
):
    with localcontext(_calculation_context(rounding)):
        salary_days = standard_month_salary_days(
            relationship.start_date, relationship.end_date, start
        )
        values = {
            code: value_cell(
                code,
                value,
                "Identificación del periodo",
                str(value),
                "No es un importe calculado.",
            )
            for code, value in (
                ("A", str(relationship.employee)),
                ("B", f"{start:%m/%Y}"),
                ("C", start.isoformat()),
            )
        }
        try:
            segments = condition_segments(
                relationship, relationship.conditions.all(), start
            )
        except InvalidBaseSalaryInput as error:
            row = report_result(
                relationship,
                start,
                values,
                [str(error)],
                salary_days,
                False,
                (),
            )
        else:
            earnings, issues = _segmented_values(
                relationship, start, segments, salary_days, rounding
            )
            values.update(earnings)
            conditions = [segment["condition"] for segment in segments]
            first = conditions[0]
            requires_hours = False
            coverage_issues = [
                issue
                for condition in conditions
                for issue in monthly_contract_issues(condition)
            ]
            if start.year != 2026:
                coverage_issues.append(
                    "No están implementadas las reglas de este ejercicio."
                )
            if any(
                condition.working_time_percentage < 100
                for condition in conditions
            ):
                coverage_issues.append(
                    "Tramos de jornada parcial: faltan las horas reales de cada tramo para comprobar sus mínimos; no se reparte automáticamente el total mensual de horas."
                )
            for field, label in (
                ("contribution_group", "grupo de cotización"),
                ("occupational_risk_rate", "tipo AT/EP"),
            ):
                if (
                    any(
                        getattr(condition, field) is None
                        for condition in conditions
                    )
                    or len(
                        {getattr(condition, field) for condition in conditions}
                    )
                    != 1
                ):
                    coverage_issues.append(
                        f"Falta o cambia el {label} dentro del mes: cotización por ese cambio pendiente."
                    )
            modes = {condition.payments_per_year for condition in conditions}
            if (
                len(modes) != 1
                or len(extra_estimate["payment_modalities"]) > 1
            ):
                coverage_issues.append(
                    "Cambio entre 12 y 14 pagas: transición pendiente."
                )
            extras = (
                extra_estimate["amount"] if modes == {14} else Decimal("0.00")
            )
            annual_days = (
                extra_estimate["annual_salary_days"] if modes == {14} else 360
            )
            if extras is None:
                coverage_issues.extend(extra_estimate["issues"])
            issues.extend(coverage_issues)
            if not coverage_issues and "W" in values:
                days = monthly_contribution_days(
                    relationship.start_date, relationship.end_date, start
                )
                try:
                    result = calculate_condition_change_contributions_2026(
                        tuple(
                            (
                                segment["values"]["W"],
                                segment["contribution_days"],
                            )
                            for segment in segments
                        ),
                        extras,
                        annual_days,
                        first.contribution_group,
                        first.occupational_risk_rate,
                        rounding,
                    )
                except InvalidPayrollInput as error:
                    issues.append(str(error))
                else:
                    values.update(contribution_cells(result, first))
                    values["AC"]["note"] += (
                        " El límite inferior mostrado incorpora el ajuste mínimo de cada tramo antes de aplicar un único máximo mensual."
                    )
                    values["CB"] = value_cell(
                        "CB",
                        values["W"]["value"] + result.employer_contributions,
                        "Bruto mensual + cuotas de empresa",
                        f"{values['W']['value']} + {result.employer_contributions}",
                        "Mínimos comprobados por tramo; máximo y solidaridad una vez sobre el total mensual, sin duplicarlos por sueldo.",
                    )
                    if "BZ" in values and all(
                        code in values for code in ("Q", "R", "S", "T")
                    ):
                        insurance = sum(
                            values[code]["value"]
                            for code in ("Q", "R", "S", "T")
                        )
                        for code in ("CA", "CG"):
                            values[code] = value_cell(
                                code,
                                values["W"]["value"]
                                - result.employee_contributions
                                - values["BZ"]["value"]
                                - insurance,
                                "Bruto − SS trabajador − IRPF del pago mensual − seguros",
                                f"{values['W']['value']} − {result.employee_contributions} − {values['BZ']['value']} − {insurance}",
                                "Se usa el tipo informado común del pago mensual; un cambio de tipo requiere concretar el pago. No se calcula una regularización automática.",
                            )
                    for code in ("X", "Z", "AC"):
                        if modes == {14}:
                            values[code]["annual_extra_estimate"] = (
                                extra_estimate
                            )
                    for cell in values.values():
                        cell["contribution_period"] = {
                            "salary_days": salary_days,
                            "contribution_days": days,
                            "annual_salary_days": annual_days,
                            "estimated_extras": extras,
                            "accrual": result.extra_payment_accrual,
                            "worked_hours": worked_hours
                            if requires_hours
                            else None,
                            "minimum_common_base": result.minimum_common_base,
                            "minimum_professional_base": result.minimum_professional_base,
                        }
            row = report_result(
                relationship,
                start,
                values,
                issues,
                salary_days,
                requires_hours,
                segments,
            )
        for cell in row["cells"]:
            cell["rounding"] = rounding
        return row
