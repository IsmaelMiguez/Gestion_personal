from functools import wraps
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.vary import vary_on_headers
from django_htmx.http import HttpResponseClientRedirect

from .forms import (
    EmployeeForm,
    EmployeeRegistrationConditionForm,
    EmploymentConditionForm,
    EmploymentRelationshipForm,
)
from .models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from .services import register_employee


@require_GET
@vary_on_headers("HX-Request")
def home(request):
    template = (
        "employees/partials/home_content.html"
        if request.htmx
        else "employees/home.html"
    )
    return render(request, template)


def staff_required(view):
    """Keep personal data restricted, including HTMX session expiry."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = (
                reverse("admin:login")
                + "?"
                + urlencode(
                    {
                        "next": request.path,
                    }
                )
            )
            if request.htmx:
                return HttpResponseClientRedirect(login_url)
            return redirect(login_url)
        if not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_GET
def employee_list(request):
    query = request.GET.get("q", "").strip()
    employees = Employee.objects.order_by("last_name", "first_name", "pk")
    for term in query.split():
        employees = employees.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(internal_code__icontains=term)
            | Q(tax_id__icontains=term)
        )
    page = Paginator(employees, 20).get_page(request.GET.get("page"))
    template = (
        "employees/partials/employee_results.html"
        if request.htmx and not request.htmx.history_restore_request
        else "employees/list.html"
    )
    return render(request, template, {"page": page, "query": query})


def condition_display(condition):
    form = EmploymentConditionForm(instance=condition)
    amounts = []
    for storage_name in EmploymentCondition.money_fields:
        field = form[storage_name.removesuffix("_cents")]
        value = field.value()
        amounts.append(
            {
                "label": field.label,
                "value": format(value, ".2f")
                if value is not None
                else "Sin informar",
            }
        )
    rate = form["withholding_rate"].value()
    return {
        "condition": condition,
        "amounts": amounts,
        "withholding_rate": format(rate, ".2f")
        if rate is not None
        else "Sin informar",
    }


@never_cache
@vary_on_headers("HX-Request")
@staff_required
@require_GET
def employee_detail(request, pk):
    relationships = (
        EmploymentRelationship.objects.select_related("company")
        .prefetch_related(
            Prefetch(
                "conditions",
                queryset=EmploymentCondition.objects.order_by(
                    "-valid_from", "-pk"
                ),
            )
        )
        .order_by("-start_date", "-pk")
    )
    employee = get_object_or_404(
        Employee.objects.prefetch_related(
            Prefetch("employment_relationships", queryset=relationships)
        ),
        pk=pk,
    )
    contracts = [
        {
            "relationship": relationship,
            "conditions": [
                condition_display(item)
                for item in relationship.conditions.all()
            ],
        }
        for relationship in employee.employment_relationships.all()
    ]
    return render(
        request,
        "employees/detail.html",
        {
            "employee": employee,
            "contracts": contracts,
        },
    )


def registration_errors(forms, error):
    """Attach model validation errors to their visible form fields."""
    field_errors = (
        error.message_dict
        if hasattr(error, "message_dict")
        else {
            "__all__": error.messages,
        }
    )
    for name, messages in field_errors.items():
        visible_name = (
            "withholding_rate"
            if name == "withholding_rate_basis_points"
            else name.removesuffix("_cents")
        )
        target = next(
            (form for form in forms if visible_name in form.fields),
            forms[-1],
        )
        target.add_error(
            visible_name if visible_name in target.fields else None, messages
        )


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def employee_registration(request):
    data = request.POST if request.method == "POST" else None
    employee_form = EmployeeForm(data=data, prefix="employee")
    relationship_form = EmploymentRelationshipForm(
        data=data, prefix="contract"
    )
    condition_form = EmployeeRegistrationConditionForm(
        data=data, prefix="condition"
    )
    forms = (employee_form, relationship_form, condition_form)
    if request.method == "POST":
        validities = [form.is_valid() for form in forms]
        if all(validities):
            try:
                employee = register_employee(
                    employee_form.save(commit=False),
                    relationship_form.save(commit=False),
                    condition_form.save(commit=False),
                )
            except ValidationError as error:
                registration_errors(forms, error)
            else:
                destination = reverse("employees:detail", args=[employee.pk])
                if request.htmx:
                    return HttpResponseClientRedirect(destination)
                return redirect(destination)
    template = (
        "employees/partials/registration_form.html"
        if request.htmx and not request.htmx.history_restore_request
        else "employees/registration.html"
    )
    return render(
        request,
        template,
        {
            "employee_form": employee_form,
            "relationship_form": relationship_form,
            "condition_form": condition_form,
            "has_errors": any(form.errors for form in forms)
            if data is not None
            else False,
            "has_companies": Company.objects.exists(),
        },
    )
