from datetime import date
from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator

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
        label="Confirmo que los periodos y el ejercicio anual usado para estimar las extras no tienen incidencias, bonus, "
        "pluriempleo, bonificaciones, horas complementarias/extraordinarias, trabajo concentrado ni cotizaciones especiales.",
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


class PayrollHoursForm(BootstrapFormMixin, forms.Form):
    use_required_attribute = False

    worked_hours = forms.DecimalField(
        label="Horas ordinarias trabajadas",
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=5,
        error_messages={
            "required": "Introduce las horas de este trabajador y mes."
        },
        widget=forms.NumberInput(
            attrs={
                "form": "report-filters",
                "data-payroll-hours": "",
                "aria-label": "Horas ordinarias trabajadas",
            }
        ),
    )

    def __init__(self, maximum_hours, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["worked_hours"].max_value = maximum_hours
        self.fields["worked_hours"].validators.append(
            MaxValueValidator(maximum_hours)
        )
        self.fields["worked_hours"].widget.attrs["max"] = maximum_hours
