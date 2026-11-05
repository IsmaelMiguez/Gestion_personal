from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers

from frontend.pages.access import staff_required
from payroll_engine.base_salary import InvalidBaseSalaryInput
from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_ordinary_payroll_2026,
)

from .payroll_forms import OrdinaryPayrollForm


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def ordinary_payroll(request):
    """Preview the base-only example without persisting payroll records."""
    form = OrdinaryPayrollForm(
        data=request.POST if request.method == "POST" else None
    )
    result = None
    if request.method == "POST" and form.is_valid():
        try:
            result = calculate_ordinary_payroll_2026(**form.cleaned_data)
        except (InvalidBaseSalaryInput, InvalidPayrollInput) as error:
            field = (
                "annual_base_salary"
                if error.field == "amount"
                else error.field
            )
            form.add_error(field if field in form.fields else None, str(error))
    template = (
        "pages/payroll/simulation/partials/workspace.html"
        if request.htmx and not request.htmx.history_restore_request
        else "pages/payroll/simulation/index.html"
    )
    return render(request, template, {"form": form, "result": result})
