from datetime import date

from django import forms

from .forms import BootstrapFormMixin
from .models import Company, Employee
from .payroll_columns import COLUMNS
from .payroll_forms import OrdinaryPayrollForm


class PayrollReportForm(BootstrapFormMixin, forms.Form):
    companies = forms.ModelMultipleChoiceField(
        label="Empresas",
        queryset=Company.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    employees = forms.ModelMultipleChoiceField(
        label="Trabajadores",
        queryset=Employee.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    years = forms.TypedMultipleChoiceField(label="Años", coerce=int)
    months = forms.TypedMultipleChoiceField(
        label="Meses",
        coerce=int,
        widget=forms.CheckboxSelectMultiple,
    )
    columns = forms.MultipleChoiceField(
        label="Campos",
        choices=COLUMNS,
        widget=forms.CheckboxSelectMultiple,
    )
    rounding = OrdinaryPayrollForm.base_fields["rounding"]
    base_only = forms.BooleanField(
        label="Confirmo que los periodos seleccionados no tienen incidencias, bonus, "
        "pluriempleo, bonificaciones ni cotizaciones especiales.",
        help_text="Los conceptos adicionales registrados se comprobarán igualmente.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["companies"].queryset = Company.objects.order_by(
            "name", "pk"
        )
        ids = (
            self.data.getlist("companies")
            if self.is_bound
            else self.initial.get("companies", [])
        )
        ids = [
            int(value)
            for value in ids
            if str(value).isdecimal() and len(str(value)) < 19
        ]
        self.fields["employees"].queryset = (
            Employee.objects.filter(
                employment_relationships__company_id__in=ids
            )
            .distinct()
            .order_by("last_name", "first_name", "pk")
        )
        self.fields["years"].choices = [
            (year, str(year))
            for year in range(2026, max(2026, date.today().year) + 2)
        ]
        self.fields["months"].choices = list(
            enumerate(
                (
                    "Enero",
                    "Febrero",
                    "Marzo",
                    "Abril",
                    "Mayo",
                    "Junio",
                    "Julio",
                    "Agosto",
                    "Septiembre",
                    "Octubre",
                    "Noviembre",
                    "Diciembre",
                ),
                start=1,
            )
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs["class"] = "form-check-input"

    def clean(self):
        values = super().clean()
        count = (
            len(values.get("employees", []))
            * len(values.get("years", []))
            * len(values.get("months", []))
        )
        if count > 240:
            raise forms.ValidationError(
                "Selecciona como máximo 240 combinaciones por consulta."
            )
        return values
