from django.test import SimpleTestCase


class FrontendShellTests(SimpleTestCase):
    def test_login_renders_shell_with_local_assets_and_csrf(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, '<html lang="es">')
        self.assertContains(
            response, "/static/vendor/bootstrap/bootstrap.min.css"
        )
        self.assertContains(response, "/static/django_htmx/htmx-2.min.js")
        self.assertContains(response, "x-csrftoken")
        self.assertIn("csrftoken", response.cookies)
        self.assertNotContains(response, "https://cdn.")

    def test_entry_redirects_to_login(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/login/")

    def test_required_static_files_are_available_to_django(self):
        from django.contrib.staticfiles import finders

        for path in (
            "vendor/bootstrap/bootstrap.min.css",
            "vendor/bootstrap/bootstrap.bundle.min.js",
            "django_htmx/htmx-2.min.js",
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path))
