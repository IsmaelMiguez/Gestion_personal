from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class ApplicationPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="staff-login",
            password="Test-login-only-123",
            is_staff=True,
        )
        cls.ordinary = get_user_model().objects.create_user(
            username="ordinary-login", password="Test-login-only-123"
        )
        cls.inactive = get_user_model().objects.create_user(
            username="inactive-login",
            password="Test-login-only-123",
            is_staff=True,
            is_active=False,
        )

    def test_login_creates_session_and_opens_payroll(self):
        response = self.client.post(
            reverse("pages:login"),
            {
                "username": "staff-login",
                "password": "Test-login-only-123",
            },
        )
        self.assertRedirects(response, reverse("employees:home"))
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), self.staff.pk
        )
        self.assertRedirects(self.client.get("/"), reverse("employees:home"))

    def test_login_returns_to_requested_internal_page(self):
        target = reverse("employees:list")
        response = self.client.get(target)
        self.assertRedirects(
            response,
            reverse("pages:login") + "?next=" + target,
            fetch_redirect_response=False,
        )
        response = self.client.post(
            reverse("pages:login"),
            {
                "username": "staff-login",
                "password": "Test-login-only-123",
                "next": target,
            },
        )
        self.assertRedirects(response, target)

    def test_external_next_is_rejected(self):
        response = self.client.post(
            reverse("pages:login"),
            {
                "username": "staff-login",
                "password": "Test-login-only-123",
                "next": "https://outside.example/login",
            },
        )
        self.assertRedirects(response, reverse("employees:home"))

    def test_wrong_password_has_generic_error_and_no_session(self):
        response = self.client.post(
            reverse("pages:login"),
            {
                "username": "staff-login",
                "password": "Wrong-password",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "El usuario o la contraseña no son correctos."
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(response, 'value="Wrong-password"')

    def test_inactive_and_non_staff_accounts_cannot_log_in(self):
        for username in ("ordinary-login", "inactive-login"):
            with self.subTest(username=username):
                response = self.client.post(
                    reverse("pages:login"),
                    {
                        "username": username,
                        "password": "Test-login-only-123",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("pages:logout")).status_code, 405
        )
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("pages:logout"))
        self.assertRedirects(response, reverse("pages:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(
            self.client.get(reverse("employees:list")).status_code, 302
        )

    def test_login_and_logout_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("pages:login"),
            {
                "username": "staff-login",
                "password": "Test-login-only-123",
            },
        )
        self.assertEqual(response.status_code, 403)
        client.force_login(self.staff)
        self.assertEqual(client.post(reverse("pages:logout")).status_code, 403)
        self.assertIn("_auth_user_id", client.session)

    def test_documents_has_independent_layout_and_no_document_functionality(
        self,
    ):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("pages:documents"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pages/documents/index.html")
        self.assertTemplateNotUsed(response, "pages/payroll/base.html")
        self.assertContains(response, "Próximamente")
        self.assertNotContains(response, 'aria-label="Navegación de Nóminas"')
        self.assertContains(
            response, 'aria-label="Secciones de la aplicación"'
        )

    def test_documents_and_payroll_require_staff(self):
        for url in (reverse("pages:documents"), reverse("employees:home")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.ordinary)
        for url in (reverse("pages:documents"), reverse("employees:home")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_expired_htmx_session_redirects_to_own_login(self):
        response = self.client.get(
            reverse("employees:list"), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["HX-Redirect"].startswith(reverse("pages:login"))
        )

    def test_logged_in_login_redirect_and_htmx_login_success(self):
        self.client.force_login(self.staff)
        self.assertRedirects(
            self.client.get(reverse("pages:login")), reverse("employees:home")
        )
        self.client.logout()
        response = self.client.post(
            reverse("pages:login"),
            {
                "username": "staff-login",
                "password": "Test-login-only-123",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(
            response.headers["HX-Redirect"], reverse("employees:home")
        )
