from itertools import groupby

from django import forms
from django.db.models import Prefetch
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.vary import vary_on_headers

from frontend.pages.access import staff_required

from .models import EmploymentCondition, EmploymentRelationship
from .payroll_columns import COLUMNS, column_group
from .payroll_report import report_row
from .payroll_report_forms import PayrollReportForm


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def payroll_report(request):
    form = PayrollReportForm(
        data=request.POST if request.method == "POST" else None
    )
    refreshing = request.POST.get("load_workers") == "1"
    if refreshing:
        form = PayrollReportForm(
            initial={
                name: request.POST.getlist(name)
                if isinstance(field, forms.MultipleChoiceField)
                else request.POST.get(name)
                for name, field in form.fields.items()
            }
        )
    rows = []
    selected_columns = []
    detail = None
    cell_key = request.POST.get("cell", "")
    if request.method == "POST" and not refreshing and form.is_valid():
        data = form.cleaned_data
        selected = set(data["columns"])
        selected_columns = [
            (code, label) for code, label in COLUMNS if code in selected
        ]
        relationships = (
            EmploymentRelationship.objects.filter(
                company__in=data["companies"],
                employee__in=data["employees"],
            )
            .select_related("company", "employee")
            .prefetch_related(
                Prefetch(
                    "conditions",
                    queryset=EmploymentCondition.objects.order_by(
                        "valid_from"
                    ),
                )
            )
            .order_by(
                "company__name", "employee__last_name", "employee_id", "pk"
            )
        )
        if (
            relationships.count() * len(data["years"]) * len(data["months"])
            > 240
        ):
            form.add_error(
                None,
                "Hay más de 240 filas: reduce los trabajadores o los periodos.",
            )
            relationships = []
        for relationship in relationships:
            for year in sorted(data["years"]):
                for month in sorted(data["months"]):
                    row = report_row(
                        relationship, year, month, data["rounding"]
                    )
                    row["cells"] = [
                        cell
                        for cell in row["cells"]
                        if cell["code"] in selected
                    ]
                    rows.append(row)
                    for cell in row["cells"]:
                        if cell["key"] == cell_key:
                            detail = cell
        if len(rows) > 240:
            form.add_error(
                None,
                "Hay más de 240 filas: reduce los trabajadores o los periodos.",
            )
            rows = []
            detail = None
        if cell_key and detail is None:
            form.add_error(
                None,
                "La celda ya no pertenece a los filtros actuales. Vuelve a calcular la tabla.",
            )
    groups = [
        (name, list(items))
        for name, items in groupby(
            form["columns"],
            key=lambda widget: column_group(widget.data["value"]),
        )
    ]
    context = {
        "form": form,
        "rows": rows,
        "columns": selected_columns,
        "column_groups": groups,
        "detail": detail,
    }
    if request.htmx and cell_key and not request.htmx.history_restore_request:
        return render(
            request, "pages/payroll/calculation/partials/detail.html", context
        )
    template = (
        "pages/payroll/calculation/partials/workspace.html"
        if request.htmx and not request.htmx.history_restore_request
        else "pages/payroll/calculation/index.html"
    )
    return render(request, template, context)


@never_cache
@vary_on_headers("HX-Request")
@staff_required
@require_GET
def payroll_workers(request):
    form = PayrollReportForm(data=request.GET)
    return render(
        request,
        "pages/payroll/calculation/partials/workers.html",
        {"form": form},
    )
