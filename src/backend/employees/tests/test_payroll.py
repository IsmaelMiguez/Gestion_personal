from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from ..models import Employee


class PayrollSimulationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="payroll-staff", is_staff=True
        )
        self.client.force_login(self.user)
        self.url = reverse("employees:simulation")
        self.values = {
            "annual_base_salary": "28000.00",
            "payments_per_year": "14",
            "contribution_group": "5",
            "withholding_rate": "15.00",
            "occupational_risk_rate": "1.50",
            "rounding": ROUND_HALF_UP,
        }

    def test_initial_page_explains_scope_and_does_not_invent_inputs(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "pages/payroll/simulation/index.html"
        )
        self.assertContains(response, "Tu nómina, paso a paso")
        self.assertContains(response, "sin complementos")
        self.assertContains(response, 'hx-post="' + self.url + '"')
        self.assertIsNone(response.context["result"])
        self.assertIsNone(
            response.context["form"]["annual_base_salary"].value()
        )
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_post_displays_calculated_breakdown_without_creating_employees(
        self,
    ):
        response = self.client.post(self.url, self.values)
        self.assertEqual(response.status_code, 200)
        result = response.context["result"]
        self.assertEqual(result.net_amount, Decimal("1548.33"))
        self.assertEqual(result.employee_contributions, Decimal("151.67"))
        self.assertContains(response, "1\u00a0548,33 €")
        for text in (
            "Contingencias comunes",
            "Solidaridad 3",
            "Del bruto al líquido",
            "Diferencia anual",
        ):
            self.assertContains(response, text)
        self.assertEqual(Employee.objects.count(), 0)

    def test_htmx_returns_workspace_and_history_restore_returns_full_page(
        self,
    ):
        response = self.client.post(
            self.url, self.values, HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, 'id="simulation-workspace"')
        self.assertNotContains(response, "<!doctype html>")
        self.assertIn("HX-Request", response.headers["Vary"])
        response = self.client.get(
            self.url,
            HTTP_HX_REQUEST="true",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
        )
        self.assertContains(response, "<!doctype html>")

    def test_invalid_inputs_preserve_form_and_remove_previous_result(self):
        for field, value in (
            ("annual_base_salary", "-1"),
            ("contribution_group", "8"),
            ("payments_per_year", "13"),
            ("withholding_rate", "100.01"),
            ("occupational_risk_rate", ""),
            ("rounding", "UNKNOWN"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    self.url,
                    {**self.values, field: value},
                    HTTP_HX_REQUEST="true",
                )
                self.assertIn(field, response.context["form"].errors)
                self.assertIsNone(response.context["result"])
                self.assertContains(response, "Revisa los campos")

    def test_access_and_csrf_are_required_for_calculation(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        response = self.client.post(
            self.url, self.values, HTTP_HX_REQUEST="true"
        )
        self.assertIn("HX-Redirect", response.headers)
        self.assertNotContains(response, "Líquido a percibir")
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
