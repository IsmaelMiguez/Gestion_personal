from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

from django import forms

from payroll_engine.base_salary import MAX_INPUT_AMOUNT

from .forms import BootstrapFormMixin


class OrdinaryPayrollForm(BootstrapFormMixin, forms.Form):
    annual_base_salary = forms.DecimalField(
        label="Sueldo base anual (€)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal(0),
        max_value=MAX_INPUT_AMOUNT,
        help_text="Solo sueldo base, sin antigüedad, seguros ni complementos.",
    )
    payments_per_year = forms.TypedChoiceField(
        label="Número de pagas",
        coerce=int,
        choices=(
            ("", "Selecciona las pagas"),
            (12, "12 pagas"),
            (14, "14 pagas"),
        ),
    )
    contribution_group = forms.TypedChoiceField(
        label="Grupo de cotización mensual",
        coerce=int,
        choices=(
            ("", "Selecciona un grupo"),
            *((group, f"Grupo {group}") for group in range(1, 8)),
        ),
    )
    withholding_rate = forms.DecimalField(
        label="IRPF informado (%)",
        max_digits=5,
        decimal_places=2,
        min_value=Decimal(0),
        max_value=Decimal(100),
        help_text="Introduce el tipo ya determinado para este supuesto.",
    )
    occupational_risk_rate = forms.DecimalField(
        label="Tipo total AT/EP (%)",
        max_digits=5,
        decimal_places=2,
        min_value=Decimal(0),
        max_value=Decimal(100),
        help_text="Tipo aplicable a la actividad u ocupación. No se deduce del grupo.",
    )
    rounding = forms.ChoiceField(
        label="Redondeo a céntimos",
        choices=(
            ("", "Selecciona una política"),
            (ROUND_HALF_UP, "Al más próximo; empate hacia arriba"),
            (ROUND_HALF_EVEN, "Al más próximo; empate al par"),
            (ROUND_DOWN, "Truncar"),
        ),
        help_text="Selecciona la política que quieres contrastar con tu software.",
    )
