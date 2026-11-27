"""Manage NCM periods from the employee's contract history."""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers
from django_htmx.http import HttpResponseClientRedirect

from frontend.pages.access import staff_required

from .forms import DeletionConfirmationForm, NcmPeriodForm
from .models import EmploymentRelationship, NcmPeriod
from .services import save_ncm_period
from .views import form_validation_errors


def _return_to_employee(request, employee_pk):
    destination = reverse("employees:detail", args=[employee_pk])
    if request.htmx:
        return HttpResponseClientRedirect(destination)
    return redirect(destination)


def _period_form_response(request, period):
    form = NcmPeriodForm(
        data=request.POST if request.method == "POST" else None,
        instance=period,
    )
    if request.method == "POST" and form.is_valid():
        try:
            save_ncm_period(form.save(commit=False))
        except ValidationError as error:
            form_validation_errors((form,), error)
        else:
            return _return_to_employee(
                request, period.employment_relationship.employee_id
            )
    template = (
        "pages/payroll/employees/partials/ncm_form.html"
        if request.htmx and not request.htmx.history_restore_request
        else "pages/payroll/employees/ncm_form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "period": period,
            "relationship": period.employment_relationship,
            "employee": period.employment_relationship.employee,
        },
    )


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def ncm_add(request, employee_pk, relationship_pk):
    relationship = get_object_or_404(
        EmploymentRelationship.objects.select_related("employee", "company"),
        pk=relationship_pk,
        employee_id=employee_pk,
    )
    return _period_form_response(
        request, NcmPeriod(employment_relationship=relationship)
    )


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def ncm_edit(request, employee_pk, pk):
    period = get_object_or_404(
        NcmPeriod.objects.select_related(
            "employment_relationship__employee",
            "employment_relationship__company",
        ),
        pk=pk,
        employment_relationship__employee_id=employee_pk,
    )
    return _period_form_response(request, period)


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def ncm_delete(request, employee_pk, pk):
    period = get_object_or_404(
        NcmPeriod.objects.select_related(
            "employment_relationship__employee",
            "employment_relationship__company",
        ),
        pk=pk,
        employment_relationship__employee_id=employee_pk,
    )
    form = DeletionConfirmationForm(
        data=request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        period.delete()
        return _return_to_employee(request, employee_pk)
    template = (
        "pages/payroll/employees/partials/ncm_delete.html"
        if request.htmx and not request.htmx.history_restore_request
        else "pages/payroll/employees/ncm_delete.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "period": period,
            "employee": period.employment_relationship.employee,
        },
    )
