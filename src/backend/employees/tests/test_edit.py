from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from ..services import create_record


class EmployeeEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="employee-editor", is_staff=True
        )
        self.client.force_login(self.user)
        self.employee = create_record(
            Employee,
            {
                "internal_code": "EMP-EDIT",
                "first_name": "Alex",
                "last_name": "Example",
                "birth_date": date(1990, 1, 1),
                "identification_type": "PASSPORT",
                "tax_id": "DOCUMENT-EDIT",
            },
        )
        self.url = reverse("employees:edit", args=[self.employee.pk])
        self.detail_url = reverse("employees:detail", args=[self.employee.pk])
        self.payload = {
            "employee-internal_code": "EMP-EDIT",
            "employee-first_name": "Alexandra",
            "employee-last_name": "Example Updated",
            "employee-birth_date": "1991-02-03",
            "employee-identification_type": "NIE",
            "employee-tax_id": "SYNTHETIC-UPDATED",
        }

    def test_edit_link_and_prefilled_form(self):
        self.assertContains(self.client.get(self.detail_url), self.url)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Alex"')
        self.assertContains(response, 'value="1990-01-01"')
        self.assertContains(response, 'value="PASSPORT" selected')
        self.assertContains(response, self.detail_url)
        self.assertNotIn("company", response.context["form"].fields)

    def test_edit_updates_identity_without_touching_contract_or_salary(self):
        company = create_record(
            Company,
            {
                "name": "Example",
                "tax_id": "COMPANY-EDIT",
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
        create_record(
            EmploymentCondition,
            {
                "employment_relationship": relationship,
                "valid_from": date(2026, 1, 1),
                "valid_until": None,
                "contract_type": "Test",
                "working_time_percentage": "100",
                "social_security_regime": "Test",
                "collective_agreement": "Test",
                "salary_amount_cents": 3000001,
                "salary_period": "ANNUAL",
                "payments_per_year": 14,
            },
        )
        original_contract = EmploymentRelationship.objects.values().get()
        original_condition = EmploymentCondition.objects.values().get()
        response = self.client.post(
            self.url,
            {
                **self.payload,
                "salary_amount_cents": "1",
                "company": "999",
                "contract-start_date": "2020-01-01",
            },
        )
        self.assertRedirects(response, self.detail_url)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, "Alexandra")
        self.assertEqual(self.employee.last_name, "Example Updated")
        self.assertEqual(self.employee.birth_date, date(1991, 2, 3))
        self.assertEqual(self.employee.identification_type, "NIE")
        self.assertEqual(self.employee.tax_id, "SYNTHETIC-UPDATED")
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(
            EmploymentRelationship.objects.values().get(), original_contract
        )
        self.assertEqual(
            EmploymentCondition.objects.values().get(), original_condition
        )

    def test_invalid_htmx_submission_keeps_input_and_database_unchanged(self):
        response = self.client.post(
            self.url,
            {
                **self.payload,
                "employee-birth_date": "invalid-date",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="employee-edit-panel"')
        self.assertContains(response, 'value="Alexandra"')
        self.assertContains(response, "No se han guardado los cambios")
        self.assertNotContains(response, "<!doctype html>")
        self.assertIn("birth_date", response.context["form"].errors)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, "Alex")

    def test_duplicate_code_does_not_change_either_employee(self):
        other = create_record(
            Employee,
            {
                "internal_code": "EMP-OTHER",
                "first_name": "Other",
                "last_name": "Example",
                "birth_date": date(1990, 1, 1),
            },
        )
        response = self.client.post(
            self.url,
            {
                **self.payload,
                "employee-internal_code": other.internal_code,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("internal_code", response.context["form"].errors)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.internal_code, "EMP-EDIT")
        self.assertEqual(self.employee.first_name, "Alex")
        self.assertEqual(Employee.objects.count(), 2)

    def test_htmx_success_redirects_to_employee_detail(self):
        response = self.client.post(
            self.url, self.payload, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.headers["HX-Redirect"], self.detail_url)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, "Alexandra")

    def test_edit_requires_staff_csrf_and_existing_employee(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload).status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("employees:edit", args=[self.employee.pk + 999])
            ).status_code,
            404,
        )
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(
            self.client.post(self.url, self.payload).status_code, 403
        )
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        response = self.client.post(
            self.url, self.payload, HTTP_HX_REQUEST="true"
        )
        self.assertIn("HX-Redirect", response.headers)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, "Alex")

    def test_history_restore_returns_full_form_and_disables_caching(self):
        response = self.client.get(
            self.url,
            HTTP_HX_REQUEST="true",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
        )
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "<!doctype html>")
        self.assertIn("no-store", response.headers["Cache-Control"])
