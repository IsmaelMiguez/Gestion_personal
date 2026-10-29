from django.contrib import admin

from .forms import EmploymentConditionForm
from .models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from .services import update_record


class ValidatedAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        obj.full_clean()
        if change:
            values = {
                field.name: getattr(obj, field.name)
                for field in obj._meta.concrete_fields
                if not field.primary_key
            }
            update_record(obj, values)
        else:
            obj.save()


@admin.register(Employee)
class EmployeeAdmin(ValidatedAdmin):
    list_display = ("internal_code", "first_name", "last_name")
    search_fields = ("internal_code", "first_name", "last_name")
    list_filter = ("identification_type",)


@admin.register(Company)
class CompanyAdmin(ValidatedAdmin):
    list_display = ("name", "tax_id")


@admin.register(EmploymentRelationship)
class EmploymentRelationshipAdmin(ValidatedAdmin):
    list_display = ("employee", "company", "start_date", "end_date")


@admin.register(EmploymentCondition)
class EmploymentConditionAdmin(ValidatedAdmin):
    form = EmploymentConditionForm
    list_display = (
        "employment_relationship",
        "valid_from",
        "valid_until",
        "job_title",
        "working_time_percentage",
        "payments_per_year",
    )
    fieldsets = (
        (
            "Contrato y vigencia",
            {
                "fields": (
                    "employment_relationship",
                    "valid_from",
                    "valid_until",
                ),
            },
        ),
        (
            "Condiciones laborales",
            {
                "fields": (
                    "job_title",
                    "contract_type",
                    "working_time_percentage",
                    "social_security_regime",
                    "collective_agreement",
                ),
            },
        ),
        (
            "Retribución",
            {
                "fields": (
                    "salary_amount",
                    "salary_period",
                    "payments_per_year",
                    "fixed_supplement",
                    "withholding_rate",
                ),
            },
        ),
        (
            "Seguros (importes mensuales en euros)",
            {
                "fields": (
                    "employee_insurance_exempt",
                    "employee_insurance_taxable",
                    "family_insurance_exempt",
                    "family_insurance_taxable",
                ),
            },
        ),
    )
