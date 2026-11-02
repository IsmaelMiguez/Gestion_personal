from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from .services import create_record


class EmployeePageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff-pages", is_staff=True
        )
        self.client.force_login(self.user)
        self.employee = create_record(
            Employee,
            {
                "internal_code": "EMP-001",
                "first_name": "Alex",
                "last_name": "Example",
                "birth_date": date(1990, 1, 1),
                "tax_id": "DOCUMENT-001",
                "identification_type": "PASSPORT",
            },
        )
        self.list_url = reverse("employees:list")
        self.detail_url = reverse("employees:detail", args=[self.employee.pk])

    def test_staff_can_read_list_and_search_across_name_fields(self):
        response = self.client.get(self.list_url, {"q": "alex example"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "employees/list.html")
        self.assertContains(response, self.detail_url)
        self.assertContains(response, "Alex Example")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(response, 'hx-history="false"')
        response = self.client.get(self.list_url, {"q": "DOCUMENT-001"})
        self.assertEqual(list(response.context["page"]), [self.employee])

    def test_search_fragment_and_empty_results(self):
        response = self.client.get(
            self.list_url, {"q": "No such person"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="employee-results"')
        self.assertContains(response, "No hay coincidencias")
        self.assertNotContains(response, "DOCUMENT-001")
        self.assertNotContains(response, "<!doctype html>")
        self.assertIn("HX-Request", response.headers["Vary"])

    def test_pagination_preserves_query_and_history_restore_gets_full_page(
        self,
    ):
        Employee.objects.bulk_create(
            [
                Employee(
                    internal_code=f"PAGE-{i}",
                    first_name="Alex",
                    last_name=f"Person {i:02}",
                    birth_date=date(1990, 1, 1),
                )
                for i in range(20)
            ]
        )
        response = self.client.get(self.list_url, {"q": "Alex", "page": 1})
        self.assertEqual(len(response.context["page"]), 20)
        self.assertContains(response, "page=2")
        self.assertContains(response, "q=Alex")
        response = self.client.get(
            self.list_url,
            {"q": "Alex", "page": 2},
            HTTP_HX_REQUEST="true",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
        )
        self.assertEqual(len(response.context["page"]), 1)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, 'value="Alex"')

    def test_detail_shows_contract_history_and_exact_amounts(self):
        company = create_record(
            Company,
            {
                "name": "Company example",
                "tax_id": "SYNTHETIC-COMPANY",
            },
        )
        relationship = create_record(
            EmploymentRelationship,
            {
                "employee": self.employee,
                "company": company,
                "start_date": date(2026, 1, 1),
                "end_date": None,
                "seniority_date": date(2020, 1, 1),
            },
        )
        values = {
            "employment_relationship": relationship,
            "valid_from": date(2026, 1, 1),
            "valid_until": date(2026, 7, 1),
            "contract_type": "Indefinido",
            "working_time_percentage": "100",
            "social_security_regime": "Test",
            "collective_agreement": "Test",
            "job_title": "Administración",
            "salary_amount_cents": 3000001,
            "salary_period": "ANNUAL",
            "payments_per_year": 14,
            "fixed_supplement_cents": 0,
            "withholding_rate_basis_points": 1937,
        }
        create_record(EmploymentCondition, values)
        create_record(
            EmploymentCondition,
            {
                **values,
                "valid_from": date(2026, 7, 1),
                "valid_until": None,
                "salary_amount_cents": 3300002,
            },
        )
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        for text in (
            "Company example",
            "Administración",
            "30000.01",
            "33000.02",
            "0.00",
            "19.37",
            "Sin informar",
            "01/01/2020",
        ):
            self.assertContains(response, text)

    def test_employee_without_contract_has_clear_empty_state(self):
        response = self.client.get(self.detail_url)
        self.assertContains(
            response, "todavía no tiene relaciones laborales registradas"
        )
        self.assertEqual(
            self.client.get(
                reverse("employees:detail", args=[self.employee.pk + 999])
            ).status_code,
            404,
        )

    def test_anonymous_requests_redirect_without_exposing_fragments(self):
        self.client.logout()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("admin:login")))
        response = self.client.get(self.list_url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response.headers)
        self.assertNotContains(response, "DOCUMENT-001")
        self.assertEqual(self.client.get(self.detail_url).status_code, 302)

    def test_non_staff_cannot_read_employee_pages(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        for url in (self.list_url, self.detail_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)
                self.assertNotContains(
                    response, "DOCUMENT-001", status_code=403
                )

    def test_personal_values_are_html_escaped(self):
        self.employee.first_name = "<script>alert(1)</script>"
        self.employee.save(update_fields=["first_name"])
        response = self.client.get(self.detail_url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
