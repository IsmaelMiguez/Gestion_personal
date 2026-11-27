from decimal import Decimal

from django import forms

from .models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
    NcmPeriod,
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
        "sin antigüedad ni complementos. Los seguros se descuentan del líquido después de calcular SS e IRPF. "
        "No lo conviertas a jornada completa si el contrato es a tiempo parcial."
    )
    employee_insurance_exempt = euro_field("Seguro trabajador exento (€/mes)")
    employee_insurance_taxable = euro_field("Seguro trabajador sujeto (€/mes)")
    family_insurance_exempt = euro_field("Seguro familia exento (€/mes)")
    family_insurance_taxable = euro_field("Seguro familia sujeto (€/mes)")
    fixed_supplement = euro_field("Complemento fijo (€/mes)")
    fixed_supplement.help_text = (
        "Importe dinerario adicional en cada uno de los doce meses; informa 0 si no existe. Procede de EMPLEADOS!P3 y CALCULO_2026!U3; los 24 trabajadores del Excel tienen 0. "
        "Cotiza y tributa; no se incluye en extras ni en la base de antigüedad."
    )
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
        help_texts = {
            "contract_type": "Por ejemplo, Indefinido o Temporal. El cálculo ordinario actual admite Indefinido; General es un régimen, no una modalidad contractual.",
            "social_security_regime": "Para el cálculo ordinario actual indica Régimen General. Otros regímenes pueden registrarse, pero su cálculo queda pendiente.",
        }
        exclude = (
            *EmploymentCondition.money_fields,
            "withholding_rate_basis_points",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for storage_name in EmploymentCondition.money_fields[1:5]:
            self.fields[storage_name.removesuffix("_cents")].help_text = (
                "Prima mensual a cargo del trabajador que se descuenta del líquido tras SS e IRPF. "
                "No reduce el bruto ni la base IRPF y no genera ingreso a cuenta. "
                "Las etiquetas exento/sujeto se conservan para identificar los importes registrados."
            )
        for storage_name in EmploymentCondition.money_fields:
            name = storage_name.removesuffix("_cents")
            value = getattr(self.instance, storage_name)
            self.initial[name] = (
                Decimal(value) / 100 if value is not None else None
            )
            if (
                self.instance._state.adding
                and storage_name in EmploymentCondition.money_fields[1:]
                and value is None
            ):
                self.initial[name] = Decimal("0.00")
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
                if (
                    self.instance._state.adding
                    and storage_name in EmploymentCondition.money_fields[1:]
                    and value is None
                ):
                    value = Decimal("0.00")
                    self.cleaned_data[name] = value
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


class NcmPeriodForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = NcmPeriod
        fields = (
            "start_date",
            "end_date",
            "rest_percentage",
            "recognized_daily_base",
        )
