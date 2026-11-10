from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from ..models import Company


class CompanyRegistrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="company-staff", is_staff=True
        )
        self.client.force_login(self.user)
        self.url = reverse("employees:company-register")
        self.values = {"name": "Empresa de ejemplo", "tax_id": "TEST-COMPANY"}

    def test_create_redirects_and_company_is_available_for_employees_and_report(
        self,
    ):
        response = self.client.post(self.url, self.values, follow=True)
        self.assertRedirects(response, self.url)
        company = Company.objects.get()
        self.assertEqual(company.name, self.values["name"])
        self.assertContains(response, "registrada. Ya puedes seleccionarla")
        response = self.client.get(reverse("employees:register"))
        self.assertIn(
            company,
            response.context["relationship_form"].fields["company"].queryset,
        )
        response = self.client.get(reverse("employees:calculation"))
        self.assertIn(
            company, response.context["form"].fields["companies"].queryset
        )

    def test_duplicate_and_required_fields_do_not_create_a_company(self):
        Company.objects.create(**self.values)
        response = self.client.post(
            self.url, {**self.values, "name": "Otro nombre"}
        )
        self.assertIn("tax_id", response.context["form"].errors)
        self.assertEqual(Company.objects.count(), 1)
        self.assertContains(response, 'value="Otro nombre"')
        response = self.client.post(self.url, {"name": " ", "tax_id": ""})
        self.assertEqual(
            set(response.context["form"].errors), {"name", "tax_id"}
        )
        self.assertEqual(Company.objects.count(), 1)

    def test_htmx_fragment_success_redirect_and_history_restore(self):
        response = self.client.post(self.url, {}, HTTP_HX_REQUEST="true")
        self.assertContains(response, 'id="company-registration"')
        self.assertNotContains(response, "<!doctype html>")
        self.assertIn("HX-Request", response.headers["Vary"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        response = self.client.get(
            self.url,
            HTTP_HX_REQUEST="true",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
        )
        self.assertContains(response, "<!doctype html>")
        response = self.client.post(
            self.url, self.values, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.headers["HX-Redirect"], self.url)
        self.assertEqual(Company.objects.count(), 1)

    def test_access_and_csrf_protect_writes(self):
        self.client.logout()
        self.assertEqual(
            self.client.post(self.url, self.values).status_code, 302
        )
        response = self.client.post(
            self.url, self.values, HTTP_HX_REQUEST="true"
        )
        self.assertIn("HX-Redirect", response.headers)
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(self.url, self.values).status_code, 403
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.values).status_code, 403)
        self.assertFalse(Company.objects.exists())

    def test_navigation_and_success_message_escape_company_name(self):
        response = self.client.get(reverse("employees:register"))
        self.assertContains(response, self.url)
        response = self.client.post(
            self.url,
            {**self.values, "name": "<script>alert(1)</script>"},
            follow=True,
        )
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
