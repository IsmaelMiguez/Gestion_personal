from django.contrib.auth.forms import AuthenticationForm


class ApplicationAuthenticationForm(AuthenticationForm):
    """Use Django authentication and the same staff access as the application."""

    error_messages = {
        "invalid_login": "El usuario o la contraseña no son correctos.",
        "inactive": "Esta cuenta no tiene acceso a la aplicación.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuario"
        self.fields["password"].label = "Contraseña"
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control form-control-lg"

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise self.get_invalid_login_error()
