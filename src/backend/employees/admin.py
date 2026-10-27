from django.contrib import admin

from .models import Company, Employee, EmploymentCondition, EmploymentRelationship
from .services import update_record


class ValidatedAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        obj.full_clean()
        if change:
            values = {field: form.cleaned_data[field] for field in form.changed_data}
            update_record(obj, values)
        else:
            obj.save()


@admin.register(Employee)
class EmployeeAdmin(ValidatedAdmin):
    list_display = ("internal_code", "first_name", "last_name")
    search_fields = ("internal_code", "first_name", "last_name")


@admin.register(Company)
class CompanyAdmin(ValidatedAdmin):
    list_display = ("name", "tax_id")


@admin.register(EmploymentRelationship)
class EmploymentRelationshipAdmin(ValidatedAdmin):
    list_display = ("employee", "company", "start_date", "end_date")


@admin.register(EmploymentCondition)
class EmploymentConditionAdmin(ValidatedAdmin):
    list_display = (
        "employment_relationship", "valid_from", "valid_until",
        "working_time_percentage",
    )
