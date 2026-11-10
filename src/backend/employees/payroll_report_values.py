"""Map calculated values to Excel columns with explanations from the same data."""

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
    gross = result.salary.ordinary_payment_amount
    cells = {}
    entries = (
        (
            "I",
            result.extra_payment_accrual,
            "Importe de una extra × número de extras ÷ 12",
            f"{result.salary.extra_payment_amount} × {result.salary.extra_payments_per_year} ÷ 12",
        ),
        (
            "J",
            result.uncapped_contribution_base,
            "Bruto ordinario + prorrata de extras",
            f"{gross} + {result.extra_payment_accrual}",
        ),
        (
            "W",
            gross,
            "Suma de devengos ordinarios; en este supuesto solo sueldo base",
            str(gross),
        ),
        (
            "X",
            result.extra_payment_accrual,
            "Prorrata de extras para cotización",
            str(result.extra_payment_accrual),
        ),
        (
            "Z",
            result.uncapped_contribution_base,
            "Bruto + prorrata de extras",
            f"{gross} + {result.extra_payment_accrual}",
        ),
        (
            "AB",
            result.uncapped_contribution_base,
            "Base de trabajo sin tope; caso sin incidencias",
            str(result.uncapped_contribution_base),
        ),
        (
            "AC",
            result.common_contribution_base,
            "Mínimo y máximo de contingencias comunes según grupo",
            f"min({MAXIMUM_BASE}, max({MONTHLY_MINIMUM_BASES[condition.contribution_group - 1]}, {result.uncapped_contribution_base})) = {result.common_contribution_base}",
        ),
        (
            "AE",
            gross,
            "Retribución dineraria sujeta satisfecha en la mensualidad",
            str(gross),
        ),
        (
            "BV",
            result.employee_contributions,
            "Suma de cuotas del trabajador, incluida solidaridad",
            " + ".join(
                str(line.employee_amount) for line in result.contributions
            ),
        ),
        (
            "BW",
            result.employee_contributions,
            "Cuota de nómina; no hay cuotas vía INSS en este supuesto",
            str(result.employee_contributions),
        ),
        (
            "BY",
            result.employer_contributions,
            "Suma de cuotas de empresa, incluida solidaridad",
            " + ".join(
                str(line.employer_amount) for line in result.contributions
            ),
        ),
        (
            "BZ",
            result.withholding_amount,
            "Bruto sujeto × IRPF informado ÷ 100",
            f"{gross} × {result.withholding_rate} ÷ 100",
        ),
        (
            "CA",
            result.net_amount,
            "Bruto − SS trabajador − IRPF",
            f"{gross} − {result.employee_contributions} − {result.withholding_amount}",
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
        lower, upper = (
            ("5101.20", "5611.32"),
            ("5611.32", "7651.80"),
            ("7651.80", "sin límite"),
        )[index]
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
