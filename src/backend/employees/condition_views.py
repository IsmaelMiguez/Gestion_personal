from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers
from django_htmx.http import HttpResponseClientRedirect

from frontend.pages.access import staff_required

from .forms import ConditionChangeForm, EmployeeRegistrationConditionForm
from .models import EmploymentCondition, EmploymentRelationship
from .services import add_conditions, change_conditions
from .views import form_validation_errors


def condition_response(request, context):
    template = (
        "pages/payroll/employees/partials/condition_form.html"
        if request.htmx and not request.htmx.history_restore_request
        else "pages/payroll/employees/condition_form.html"
    )
    return render(request, template, context)


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def condition_change(request, employee_pk, pk):
    previous = get_object_or_404(
        EmploymentCondition.objects.select_related(
            "employment_relationship__employee",
            "employment_relationship__company",
        ),
        pk=pk,
        employment_relationship__employee_id=employee_pk,
    )
    values = {
        field.name: getattr(previous, field.name)
        for field in previous._meta.concrete_fields
        if not field.primary_key and not field.is_relation
    }
    values["valid_from"] = None
    form = ConditionChangeForm(
        data=request.POST if request.method == "POST" else None,
        instance=EmploymentCondition(**values),
        prefix="condition",
    )
    if request.method == "POST" and form.is_valid():
        try:
            change_conditions(previous, form.save(commit=False))
        except ValidationError as error:
            form_validation_errors((form,), error)
        else:
            destination = reverse("employees:detail", args=[employee_pk])
            if request.htmx:
                return HttpResponseClientRedirect(destination)
            return redirect(destination)
    return condition_response(
        request,
        {
            "condition_form": form,
            "previous": previous,
            "relationship": previous.employment_relationship,
            "employee": previous.employment_relationship.employee,
            "heading": "Cambiar condiciones",
        },
    )


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def condition_add(request, employee_pk, relationship_pk):
    relationship = get_object_or_404(
        EmploymentRelationship.objects.select_related("employee", "company"),
        pk=relationship_pk,
        employee_id=employee_pk,
    )
    form = EmployeeRegistrationConditionForm(
        data=request.POST if request.method == "POST" else None,
        instance=EmploymentCondition(employment_relationship=relationship),
        prefix="condition",
    )
    if request.method == "POST" and form.is_valid():
        try:
            add_conditions(relationship, form.save(commit=False))
        except ValidationError as error:
            form_validation_errors((form,), error)
        else:
            destination = reverse("employees:detail", args=[employee_pk])
            if request.htmx:
                return HttpResponseClientRedirect(destination)
            return redirect(destination)
    return condition_response(
        request,
        {
            "condition_form": form,
            "relationship": relationship,
            "employee": relationship.employee,
            "heading": "Añadir condiciones",
        },
    )
