from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, resolve_url
from django_htmx.http import HttpResponseClientRedirect


def staff_required(view):
    """Keep personal data restricted, including HTMX session expiry."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = (
                resolve_url(settings.LOGIN_URL)
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
