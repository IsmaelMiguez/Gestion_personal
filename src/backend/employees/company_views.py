from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers
from django_htmx.http import HttpResponseClientRedirect

from frontend.pages.access import staff_required

from .forms import CompanyForm
from .models import Company
from .services import create_record
from .views import form_validation_errors


@never_cache
@vary_on_headers("HX-Request", "HX-History-Restore-Request")
@staff_required
@require_http_methods(["GET", "POST"])
def company_registration(request):
    form = CompanyForm(data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            company = create_record(Company, form.cleaned_data)
        except ValidationError as error:
            form_validation_errors((form,), error)
        else:
            messages.success(
                request,
                f"Empresa «{company.name}» registrada. Ya puedes seleccionarla al registrar empleados o calcular nóminas.",
            )
            destination = reverse("employees:company-register")
            if request.htmx:
                return HttpResponseClientRedirect(destination)
            return redirect(destination)
    template = (
        "pages/payroll/companies/partials/registration_form.html"
        if request.htmx and not request.htmx.history_restore_request
        else "pages/payroll/companies/registration.html"
    )
    return render(request, template, {"form": form})
