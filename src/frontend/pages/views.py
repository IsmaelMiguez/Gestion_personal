from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_headers
from django_htmx.http import HttpResponseClientRedirect

from .access import staff_required
from .forms import ApplicationAuthenticationForm


class ApplicationLoginView(LoginView):
    template_name = "pages/login/index.html"
    authentication_form = ApplicationAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.htmx:
            return HttpResponseClientRedirect(response.url)
        return response


@never_cache
@vary_on_headers("HX-Request")
@require_GET
def entry(request):
    return redirect(
        "employees:home" if request.user.is_authenticated else "pages:login"
    )


@never_cache
@vary_on_headers("HX-Request")
@staff_required
@require_GET
def documents(request):
    return render(request, "pages/documents/index.html")
