"""Map calculated values to Excel columns with explanations from the same data."""

from decimal import Decimal

from payroll_engine.reconciliation import reconcile_ordinary_payroll
from payroll_engine.rules_2026 import MAXIMUM_BASE, MONTHLY_MINIMUM_BASES

from .payroll_columns import COLUMNS

SOURCE = "Orden PJC/297/2026, artículos 1–4, 16, 17 y 33"


def value_cell(code, value, formula, operands, note):
    return {
        "code": code,
        "label": dict(COLUMNS)[code],
        "value": value,
        "formula": formula,
        "operands": operands,
        "note": note,
        "available": True,
    }


def result_cells(result, condition):
    gross = result.gross_amount
    cells = {}
    entries = (
        (
            "W",
            gross,
            "Sueldo base ordinario + antigüedad mensual + complemento fijo dinerario",
            f"{result.salary.ordinary_payment_amount} + {result.seniority_amount} + {result.fixed_supplement_amount}",
        ),
        (
            "AE",
            result.taxable_gross_amount,
            "Bruto ordinario completo; los seguros se descuentan después del líquido",
            f"{gross} = {result.taxable_gross_amount}",
        ),
        (
            "BZ",
            result.withholding_amount,
            "Bruto ordinario × tipo IRPF informado ÷ 100",
            f"{gross} × {result.withholding_rate} ÷ 100 = {result.withholding_amount}",
        ),
        (
            "CA",
            result.net_amount,
            "Bruto − SS trabajador − IRPF − seguros descontados del líquido",
            f"{gross} − {result.employee_contributions} − {result.withholding_amount} = líquido previo {result.net_before_insurance}; "
            f"{result.net_before_insurance} − {result.insurance_amount} = transferencia {result.net_amount}",
        ),
        (
            "CB",
            result.employer_cash_cost,
            "Bruto ordinario + cuotas de empresa",
            f"{gross} + {result.employer_contributions}",
        ),
        (
            "CF",
            gross,
            "Bruto empresa; no hay prestación INSS en este supuesto",
            str(gross),
        ),
        (
            "CG",
            result.net_amount,
            "Neto empresa; no hay prestación INSS en este supuesto",
            str(result.net_amount),
        ),
    )
    for code, value, formula, operands in entries:
        cells[code] = value_cell(code, value, formula, operands, SOURCE)
    checks = reconcile_ordinary_payroll(result, result.salary.rounding)
    cells["CJ"] = value_cell(
        "CJ",
        "OK" if all(check.balanced for check in checks) else "REVISAR",
        "Conciliación de bruto, descuentos de seguros, bases, cuotas, fiscalidad, líquido y coste",
        "; ".join(
            f"{check.label}: diferencia {check.difference}" for check in checks
        ),
        "Comprueba identidades aritméticas del caso soportado. No certifica normativa, exenciones ni conceptos todavía pendientes.",
    )
    cells["CJ"]["checks"] = checks
    for code in ("AE", "BZ", "CA"):
        cells[code]["note"] = (
            "Seguros a cargo del trabajador descontados del líquido tras calcular SS e IRPF sobre el bruto completo. "
            "Los campos históricos exento/sujeto identifican primas; no reducen la base IRPF ni generan ingreso a cuenta en este perfil."
        )
    cells.update(contribution_cells(result, condition))
    return cells


def contribution_cells(result, condition):
    cells = {}
    maximum = MAXIMUM_BASE * result.contribution_days / 30
    minimum = (
        MONTHLY_MINIMUM_BASES[condition.contribution_group - 1]
        * result.contribution_days
        / 30
    )
    formula = "Estimación anual de ambas extras ÷ 12 (artículo 1)"
    operands = f"{result.estimated_annual_extra_amount} ÷ 12 = {result.extra_payment_accrual}"
    if result.annual_salary_days != 360 or result.contribution_days != 30:
        formula = "Extras estimadas ÷ días salariales cubiertos del año × días cotizados del mes"
        operands = f"{result.estimated_annual_extra_amount} ÷ {result.annual_salary_days} × {result.contribution_days} = {result.extra_payment_accrual}"
    entries = (
        ("X", result.extra_payment_accrual, formula, operands),
        (
            "Z",
            result.uncapped_contribution_base,
            "Bruto devengado + prorrata cotizable de extras",
            str(result.uncapped_contribution_base),
        ),
        (
            "AB",
            result.uncapped_contribution_base,
            "Base teórica sin incidencias",
            str(result.uncapped_contribution_base),
        ),
        (
            "AC",
            result.common_contribution_base,
            "Base común limitada por mínimos y máximos del periodo",
            f"min({maximum}, max({minimum}, {result.uncapped_contribution_base})) = {result.common_contribution_base}; días cotizados: {result.contribution_days}.",
        ),
        (
            "BV",
            result.employee_contributions,
            "Suma de cuotas del trabajador",
            " + ".join(
                str(line.employee_amount) for line in result.contributions
            ),
        ),
        (
            "BW",
            result.employee_contributions,
            "Cuotas del trabajador sin prestación INSS",
            str(result.employee_contributions),
        ),
        (
            "BY",
            result.employer_contributions,
            "Suma de cuotas de empresa",
            " + ".join(
                str(line.employer_amount) for line in result.contributions
            ),
        ),
    )
    for code, value, explanation, details in entries:
        cells[code] = value_cell(
            code,
            value,
            explanation,
            details,
            SOURCE
            + f". Días cotizados: {result.contribution_days}. Ajuste a 30 solo en meses completos; los días salariales pueden ser diferentes.",
        )
    for index, employee_code, employer_code in (
        (0, "AF", "AG"),
        (1, "AM", "AN"),
        (2, "AH", "AI"),
        (3, "AK", "AL"),
        (4, None, "AJ"),
        (5, None, "AO"),
    ):
        line = result.contributions[index]
        for code, rate, amount in (
            (employee_code, line.employee_rate, line.employee_amount),
            (employer_code, line.employer_rate, line.employer_amount),
        ):
            if code:
                cells[code] = value_cell(
                    code,
                    amount,
                    "Base aplicable × tipo ÷ 100",
                    f"{line.base} × {rate} ÷ 100",
                    SOURCE,
                )
    for index, codes in enumerate(
        (
            ("AP", "AQ", "AR", "AS", "AT"),
            ("AU", "AV", "AW", "AX", "AY"),
            ("AZ", "BA", "BB", "BC", "BD"),
        )
    ):
        line = result.contributions[index + 6]
        monthly_lower, monthly_upper = (
            ("5101.20", "5611.32"),
            ("5611.32", "7651.80"),
            ("7651.80", "Infinity"),
        )[index]
        lower = (
            Decimal(monthly_lower) * result.contribution_days / 30
        ).quantize(Decimal("0.01"))
        upper = (
            (Decimal(monthly_upper) * result.contribution_days / 30).quantize(
                Decimal("0.01")
            )
            if monthly_upper != "Infinity"
            else "sin límite"
        )
        for code, value, formula in zip(
            codes,
            (
                line.base,
                line.employee_rate,
                line.employee_amount,
                line.employer_rate,
                line.employer_amount,
            ),
            (
                "max(0, min(base sin tope, límite superior) − límite inferior)",
                "Tipo trabajador (%)",
                "Base tramo × tipo trabajador ÷ 100",
                "Tipo empresa (%)",
                "Base tramo × tipo empresa ÷ 100",
            ),
            strict=True,
        ):
            cells[code] = value_cell(
                code,
                value,
                formula,
                f"Base sin tope {result.uncapped_contribution_base}; límites {lower}–{upper}; base tramo {line.base}; tipos {line.employee_rate}% / {line.employer_rate}%.",
                SOURCE,
            )
    for code, attribute in (
        ("BT", "employee_amount"),
        ("BU", "employer_amount"),
    ):
        values = [
            getattr(line, attribute) for line in result.contributions[6:]
        ]
        cells[code] = value_cell(
            code,
            sum(values),
            "Suma de cuotas de los tres tramos",
            " + ".join(map(str, values)),
            SOURCE,
        )
    return cells


def period_result_cells(result, condition, gross, salary_days):
    cells = contribution_cells(result, condition)
    cells["CB"] = value_cell(
        "CB",
        gross + result.employer_contributions,
        "Bruto devengado + cuotas empresariales",
        f"{gross} + {result.employer_contributions}",
        "Los seguros a cargo del trabajador no se suman al coste empresarial.",
    )
    cells["AE"] = value_cell(
        "AE",
        gross,
        "Bruto devengado sujeto a IRPF",
        str(gross),
        "Los seguros se descuentan del líquido y no reducen esta base.",
    )
    if condition.withholding_rate_basis_points is None:
        return cells
    rate = Decimal(condition.withholding_rate_basis_points) / 100
    tax = (gross * rate / 100).quantize(Decimal("0.01"))
    cells["BZ"] = value_cell(
        "BZ",
        tax,
        "Bruto devengado × IRPF informado ÷ 100",
        f"{gross} × {rate} ÷ 100",
        "Se aplica el porcentaje informado; no se calcula ni regulariza el tipo.",
    )
    premiums = [
        getattr(condition, name) for name in condition.money_fields[1:5]
    ]
    if (
        salary_days == 30 and all(amount is not None for amount in premiums)
    ) or all(amount == 0 for amount in premiums):
        insurance = Decimal(sum(premiums)) / 100
        for code in ("CA", "CG"):
            cells[code] = value_cell(
                code,
                gross - result.employee_contributions - tax - insurance,
                "Bruto − SS trabajador − IRPF − seguros conocidos del periodo",
                f"{gross} − {result.employee_contributions} − {tax} − {insurance}",
                "En mes completo se descuentan las primas mensuales; en mes incompleto este líquido solo se conoce si las cuatro primas son cero. No incluye finiquito ni abono separado de extras.",
            )
    return cells
