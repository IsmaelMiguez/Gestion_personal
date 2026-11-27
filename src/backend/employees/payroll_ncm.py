"""Present recognized NCM benefits separately from pending company payroll."""

from datetime import timedelta
from decimal import Decimal, localcontext

from payroll_engine.base_salary import (
    _calculation_context,
    standard_month_salary_days,
)
from payroll_engine.ncm import InvalidNcmInput, calculate_ncm_benefit

from .payroll_report_values import pending_cell, report_result, value_cell

NCM_PAYROLL_PENDING = (
    "Hay NCM: el salario de empresa, los seguros, el complemento, las extras, "
    "las cotizaciones y los líquidos durante el permiso están pendientes de "
    "sus reglas específicas. La prestación bruta no es el líquido del INSS."
)
NCM_EXTRAS_PENDING = "Hay NCM en el semestre: falta concretar su efecto sobre el devengo de extras."


def ncm_periods_in_interval(periods, start, end):
    return [
        period
        for period in periods
        if period.start_date < end and period.end_date > start
    ]


def _monthly_benefits(relationship, periods, start, end, rounding):
    segments = []
    for period in periods:
        first = max(start, period.start_date, relationship.start_date)
        until = min(end, period.end_date, relationship.end_date or end)
        covering = [
            condition
            for condition in relationship.conditions.all()
            if condition.valid_from <= first
            and (
                condition.valid_until is None or condition.valid_until >= until
            )
        ]
        if first >= until or len(covering) != 1:
            raise InvalidNcmInput(
                "conditions",
                "Faltan condiciones únicas que cubran cada periodo NCM del mes.",
            )
        benefit = calculate_ncm_benefit(
            covering[0].working_time_percentage,
            period.rest_percentage,
            period.recognized_daily_base,
            (until - first).days,
            rounding,
        )
        segments.append(
            {
                "start": first,
                "last_day": until - timedelta(days=1),
                "result": benefit,
            }
        )
    return segments


def ncm_report_row(relationship, start, end, rounding):
    """Return an NCM-only row, or None when the ordinary report applies."""
    periods = ncm_periods_in_interval(
        relationship.ncm_periods.all(), start, end
    )
    if not periods:
        return None
    reasons = [NCM_PAYROLL_PENDING]
    values = {}
    for code, value in (
        ("A", str(relationship.employee)),
        ("B", f"{start:%m/%Y}"),
        ("C", start.isoformat()),
        ("D", "NCM"),
        ("E", "Nacimiento y cuidado del menor"),
    ):
        values[code] = value_cell(
            code,
            value,
            "Periodo NCM registrado en la relación laboral",
            str(value),
            "Las condiciones habituales del contrato se conservan.",
        )
    segments = []
    with localcontext(_calculation_context(rounding)):
        try:
            segments = _monthly_benefits(
                relationship, periods, start, end, rounding
            )
        except InvalidNcmInput as error:
            reasons.append(str(error))
        else:
            total = sum(
                (item["result"].gross_benefit for item in segments), Decimal(0)
            )
            equivalent_days = sum(
                (item["result"].equivalent_rest_days for item in segments),
                Decimal(0),
            )
            values["CC"] = value_cell(
                "CC",
                total,
                "Suma de BR diaria × descanso / 100 × días naturales de cada periodo NCM en el mes",
                " + ".join(
                    f"{item['result'].recognized_daily_base} × {item['result'].rest_percentage} / 100 × {item['result'].benefit_days} = {item['result'].gross_benefit}"
                    for item in segments
                ),
                "BR reconocida antes del descanso, ya correspondiente a la jornada contractual. Cada periodo se redondea una vez; después se suman sus importes. No incluye cuotas ni líquido del INSS.",
            )
            values["M"] = value_cell(
                "M",
                equivalent_days,
                "Suma de días naturales NCM × porcentaje de descanso / 100",
                str(equivalent_days),
                "Días equivalentes de prestación. No son días salariales ni días de cotización; no se normalizan a 30.",
            )
            for code, field, label in (
                (
                    "K",
                    "recognized_daily_base",
                    "BR diaria reconocida antes de aplicar el descanso",
                ),
                (
                    "N",
                    "rest_percentage",
                    "Descanso sobre la jornada habitual del contrato (%)",
                ),
            ):
                unique = {getattr(item["result"], field) for item in segments}
                values[code] = (
                    value_cell(
                        code,
                        unique.pop(),
                        label,
                        "Ver periodos NCM",
                        "Referencia de los días con NCM; no de los días sin permiso.",
                    )
                    if len(unique) == 1
                    else pending_cell(
                        code,
                        "Hay diferentes valores durante el mes. Consulta el desglose de periodos; no se inventa una referencia única.",
                    )
                )
            active_start = max(start, relationship.start_date)
            active_end = min(end, relationship.end_date or end)
            effective = {
                item["result"].effective_working_percentage
                for item in segments
            }
            if (
                sum(item["result"].benefit_days for item in segments)
                == (active_end - active_start).days
                and len(effective) == 1
            ):
                values["F"] = value_cell(
                    "F",
                    effective.pop(),
                    "Jornada contratada × (1 − descanso NCM / 100)",
                    "Ver jornada contratada y descanso en el desglose NCM.",
                    "Porcentaje efectivo durante todo el intervalo activo del mes. No vuelve a aplicarse a la BR ni al salario ya contratado.",
                )
            else:
                values["F"] = pending_cell(
                    "F",
                    "El NCM no cubre todo el intervalo activo o hay jornadas efectivas diferentes. El desglose muestra la jornada de cada periodo; el equivalente mensual queda pendiente.",
                )
    row = report_result(
        relationship,
        start,
        values,
        reasons,
        standard_month_salary_days(
            relationship.start_date, relationship.end_date, start
        ),
        False,
        (),
    )
    for cell in row["cells"]:
        cell["rounding"] = rounding
        cell["ncm_segments"] = segments
    return row
