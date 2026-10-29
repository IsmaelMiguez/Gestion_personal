from decimal import Decimal

from django import forms

from .models import EmploymentCondition


def euro_field(label):
    return forms.DecimalField(
        label=label, max_digits=12, decimal_places=2,
        min_value=Decimal("0"), required=False,
    )


class EmploymentConditionForm(forms.ModelForm):
    """Present euros and percentages while persisting scaled integers."""

    salary_amount = euro_field("Importe salarial (€)")
    employee_insurance_exempt = euro_field("Seguro trabajador exento (€/mes)")
    employee_insurance_taxable = euro_field("Seguro trabajador sujeto (€/mes)")
    family_insurance_exempt = euro_field("Seguro familia exento (€/mes)")
    family_insurance_taxable = euro_field("Seguro familia sujeto (€/mes)")
    fixed_supplement = euro_field("Complemento fijo (€/mes)")
    withholding_rate = forms.DecimalField(
        label="IRPF (%)", decimal_places=2, max_digits=5,
        min_value=Decimal("0"), max_value=Decimal("100"), required=False,
    )

    class Meta:
        model = EmploymentCondition
        exclude = (
            *EmploymentCondition.money_fields,
            "withholding_rate_basis_points",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for storage_name in EmploymentCondition.money_fields:
            name = storage_name.removesuffix("_cents")
            value = getattr(self.instance, storage_name)
            self.initial[name] = (
                Decimal(value) / 100 if value is not None else None
            )
        rate = self.instance.withholding_rate_basis_points
        self.initial["withholding_rate"] = (
            Decimal(rate) / 100 if rate is not None else None
        )
        if self.instance._state.adding:
            self.initial.setdefault("payments_per_year", 14)

    def _post_clean(self):
        for storage_name in EmploymentCondition.money_fields:
            name = storage_name.removesuffix("_cents")
            if name in self.cleaned_data:
                value = self.cleaned_data[name]
                setattr(
                    self.instance, storage_name,
                    int(value * 100) if value is not None else None,
                )
        if "withholding_rate" in self.cleaned_data:
            rate = self.cleaned_data["withholding_rate"]
            self.instance.withholding_rate_basis_points = (
                int(rate * 100) if rate is not None else None
            )
        super()._post_clean()
