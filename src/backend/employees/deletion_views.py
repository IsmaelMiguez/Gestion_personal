from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers
from django_htmx.http import HttpResponseClientRedirect

from frontend.pages.access import staff_required

from .forms import DeletionConfirmationForm
from .models import Employee, EmploymentCondition
from .services import delete_condition, delete_employee


def deletion_response(request, context):
    template = (
        "pages/payroll/employees/partials/delete_confirmation.html"
        if request.htmx and not request.htmx.history_restore_request
        else "pages/payroll/employees/delete_confirmation.html"
    )
    return render(request, template, context)


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    form = DeletionConfirmationForm(
        data=request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        try:
            delete_employee(employee)
        except ProtectedError:
            form.add_error(
                None,
                "El empleado tiene otros registros vinculados que impiden eliminarlo.",
            )
        else:
            destination = reverse("employees:list")
            if request.htmx:
                return HttpResponseClientRedirect(destination)
            return redirect(destination)
    return deletion_response(
        request,
        {
            "form": form,
            "employee": employee,
            "heading": "Eliminar empleado",
            "relationship_count": employee.employment_relationships.count(),
            "condition_count": EmploymentCondition.objects.filter(
                employment_relationship__employee=employee
            ).count(),
        },
    )


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def condition_delete(request, employee_pk, pk):
    condition = get_object_or_404(
        EmploymentCondition.objects.select_related(
            "employment_relationship__employee",
            "employment_relationship__company",
        ),
        pk=pk,
        employment_relationship__employee_id=employee_pk,
    )
    employee = condition.employment_relationship.employee
    form = DeletionConfirmationForm(
        data=request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        try:
            delete_condition(condition)
        except ProtectedError:
            form.add_error(
                None,
                "Este periodo tiene registros vinculados que impiden eliminarlo.",
            )
        else:
            destination = reverse("employees:detail", args=[employee_pk])
            if request.htmx:
                return HttpResponseClientRedirect(destination)
            return redirect(destination)
    return deletion_response(
        request,
        {
            "form": form,
            "employee": employee,
            "condition": condition,
            "heading": "Eliminar condiciones",
        },
    )
