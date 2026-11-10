from decimal import Decimal

from django import forms

from .models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)


def euro_field(label):
    return forms.DecimalField(
        label=label,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
    )


class EmploymentConditionForm(forms.ModelForm):
    """Present euros and percentages while persisting scaled integers."""

    salary_amount = euro_field("Sueldo base (€)")
    salary_amount.help_text = (
        "Importe correspondiente a la jornada habitual del contrato, "
        "sin antigüedad, seguros ni complementos. "
        "No lo conviertas a jornada completa si el contrato es a tiempo parcial."
    )
    employee_insurance_exempt = euro_field("Seguro trabajador exento (€/mes)")
    employee_insurance_taxable = euro_field("Seguro trabajador sujeto (€/mes)")
    family_insurance_exempt = euro_field("Seguro familia exento (€/mes)")
    family_insurance_taxable = euro_field("Seguro familia sujeto (€/mes)")
    fixed_supplement = euro_field("Complemento fijo (€/mes)")
    withholding_rate = forms.DecimalField(
        label="IRPF (%)",
        decimal_places=2,
        max_digits=5,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        required=False,
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
                    self.instance,
                    storage_name,
                    int(value * 100) if value is not None else None,
                )
        if "withholding_rate" in self.cleaned_data:
            rate = self.cleaned_data["withholding_rate"]
            self.instance.withholding_rate_basis_points = (
                int(rate * 100) if rate is not None else None
            )
        super()._post_clean()


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(
                    attrs={"type": "date"}, format="%Y-%m-%d"
                )
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
                continue
            field.widget.attrs["class"] = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )


class CompanyForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Company
        fields = ("name", "tax_id")
        labels = {
            "name": "Nombre de la empresa",
            "tax_id": "Identificación fiscal (NIF)",
        }


class EmployeeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Employee
        fields = (
            "internal_code",
            "first_name",
            "last_name",
            "birth_date",
            "identification_type",
            "tax_id",
        )


class EmploymentRelationshipForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = EmploymentRelationship
        fields = ("company", "start_date", "end_date", "seniority_date")


class EmployeeRegistrationConditionForm(
    BootstrapFormMixin, EmploymentConditionForm
):
    class Meta(EmploymentConditionForm.Meta):
        exclude = (
            *EmploymentConditionForm.Meta.exclude,
            "employment_relationship",
        )


class ConditionChangeForm(EmployeeRegistrationConditionForm):
    class Meta(EmployeeRegistrationConditionForm.Meta):
        exclude = (
            *EmployeeRegistrationConditionForm.Meta.exclude,
            "valid_until",
        )


class DeletionConfirmationForm(BootstrapFormMixin, forms.Form):
    confirm = forms.BooleanField(
        label="Confirmo que quiero eliminar los datos indicados.",
        required=True,
    )
