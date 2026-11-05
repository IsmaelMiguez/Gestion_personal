"""Monthly General Regime rules, effective 2026-01-01.

Source: Orden PJC/297/2026, articles 1–4, 16, 17 and 33:
https://www.boe.es/buscar/act.php?id=BOE-A-2026-7296
Rates are percentages, with employee first and employer second.
"""

from decimal import Decimal

MAXIMUM_BASE = Decimal("5101.20")
MINIMUM_PROFESSIONAL_BASE = Decimal("1424.40")
MONTHLY_MINIMUM_BASES = tuple(
    Decimal(value)
    for value in (
        "1989.30",
        "1649.70",
        "1435.20",
        "1424.40",
        "1424.40",
        "1424.40",
        "1424.40",
    )
)
COMMON_RATES = (Decimal("4.70"), Decimal("23.60"))
MEI_RATES = (Decimal("0.15"), Decimal("0.75"))
UNEMPLOYMENT_RATES = (Decimal("1.55"), Decimal("5.50"))
TRAINING_RATES = (Decimal("0.10"), Decimal("0.60"))
FOGASA_RATES = (Decimal(0), Decimal("0.20"))
SOLIDARITY_BANDS = (
    (MAXIMUM_BASE, Decimal("5611.32"), Decimal("0.19"), Decimal("0.96")),
    (Decimal("5611.32"), Decimal("7651.80"), Decimal("0.21"), Decimal("1.04")),
    (
        Decimal("7651.80"),
        Decimal("Infinity"),
        Decimal("0.24"),
        Decimal("1.22"),
    ),
)
