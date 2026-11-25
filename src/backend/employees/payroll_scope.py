"""Shared coverage checks for the first ordinary monthly contract profile."""

from decimal import Decimal
from unicodedata import combining, normalize


def normalized_text(value):
    return "".join(
        c for c in normalize("NFKD", value.lower()) if not combining(c)
    ).strip()


def monthly_contract_issues(condition):
    reasons = []
    if condition.working_time_percentage != Decimal(100):
        reasons.append(
            "La cotización a jornada parcial aún no está implementada."
        )
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
