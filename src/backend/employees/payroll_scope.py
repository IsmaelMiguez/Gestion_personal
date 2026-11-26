"""Shared coverage checks for the first ordinary monthly contract profile."""

from datetime import date, timedelta
from unicodedata import combining, normalize

from payroll_engine.base_salary import (
    InvalidBaseSalaryInput,
    monthly_contribution_days,
    standard_month_salary_day_splits,
)


def normalized_text(value):
    return "".join(
        c for c in normalize("NFKD", value.lower()) if not combining(c)
    ).strip()


def monthly_contract_issues(condition):
    reasons = []
    if normalized_text(condition.social_security_regime) not in (
        "general",
        "regimen general",
    ):
        reasons.append(
            "El régimen registrado no identifica el Régimen General ordinario."
        )
    if normalized_text(condition.contract_type) not in (
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
    return reasons


def condition_segments(relationship, conditions, month):
    """Require complete, non-overlapping coverage of the active month."""
    end = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    active_start = max(month, relationship.start_date)
    active_end = min(end, relationship.end_date or end)
    if active_start >= active_end:
        return []
    candidates = sorted(
        (
            condition
            for condition in conditions
            if condition.valid_from < active_end
            and (
                condition.valid_until is None
                or condition.valid_until > active_start
            )
        ),
        key=lambda condition: condition.valid_from,
    )
    cursor = active_start
    segments = []
    for condition in candidates:
        start = max(active_start, condition.valid_from)
        stop = min(active_end, condition.valid_until or active_end)
        if start != cursor:
            raise InvalidBaseSalaryInput(
                "conditions",
                "Las condiciones no cubren todo el intervalo activo del mes: hay un hueco o solapamiento.",
            )
        segments.append(
            {
                "condition": condition,
                "start": start,
                "end": stop,
                "last_day": stop - timedelta(days=1),
            }
        )
        cursor = stop
    if cursor != active_end:
        raise InvalidBaseSalaryInput(
            "conditions",
            "Faltan condiciones para cubrir todo el intervalo activo del mes.",
        )
    salary_days = standard_month_salary_day_splits(
        relationship.start_date,
        relationship.end_date,
        month,
        tuple(segment["start"] for segment in segments[1:]),
    )
    contribution_days = monthly_contribution_days(
        relationship.start_date, relationship.end_date, month
    )
    allocated = 0
    for index, (segment, days) in enumerate(
        zip(segments, salary_days, strict=True)
    ):
        segment["salary_days"] = days
        segment["contribution_days"] = (
            contribution_days - allocated
            if index == len(segments) - 1
            else (segment["end"] - segment["start"]).days
        )
        allocated += segment["contribution_days"]
    return segments
