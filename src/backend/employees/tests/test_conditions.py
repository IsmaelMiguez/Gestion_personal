from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from ..services import change_conditions, create_record


class ConditionChangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="conditions", is_staff=True
        )
        self.client.force_login(self.user)
        self.employee = create_record(
            Employee,
            {
                "internal_code": "COND-1",
                "first_name": "Alex",
                "last_name": "Example",
                "birth_date": date(1990, 1, 1),
            },
        )
        company = create_record(
            Company, {"name": "Example", "tax_id": "COND-COMPANY"}
        )
        self.relationship = create_record(
            EmploymentRelationship,
            {
                "employee": self.employee,
                "company": company,
                "start_date": date(2026, 1, 1),
                "end_date": None,
                "seniority_date": date(2020, 1, 1),
            },
        )
        self.values = {
            "employment_relationship": self.relationship,
            "valid_from": date(2026, 1, 1),
            "valid_until": None,
            "contract_type": "Indefinido",
            "working_time_percentage": "100",
            "social_security_regime": "Test",
            "collective_agreement": "Test",
            "salary_amount_cents": 3000001,
            "salary_period": "ANNUAL",
            "payments_per_year": 12,
            "employee_insurance_exempt_cents": 4219,
        }
        self.previous = create_record(EmploymentCondition, self.values)
        self.url = reverse(
            "employees:condition-change",
            args=[self.employee.pk, self.previous.pk],
        )
        self.payload = {
            "condition-valid_from": "2026-12-01",
            "condition-job_title": "Responsable",
            "condition-contract_type": "Indefinido",
            "condition-working_time_percentage": "75",
            "condition-social_security_regime": "Test",
            "condition-collective_agreement": "Test",
            "condition-salary_amount": "33000.02",
            "condition-salary_period": "ANNUAL",
            "condition-payments_per_year": "12",
            "condition-employee_insurance_exempt": "42.19",
        }

    def test_change_form_copies_values_but_requires_effective_date(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        form = response.context["condition_form"]
        self.assertEqual(str(form["salary_amount"].value()), "30000.01")
        self.assertEqual(form["payments_per_year"].value(), 12)
        self.assertIsNone(form["valid_from"].value())
        self.assertNotIn("valid_until", form.fields)
        self.assertEqual(EmploymentCondition.objects.count(), 1)

    def test_change_preserves_history_and_ignores_forged_end(self):
        response = self.client.post(
            self.url,
            {
                **self.payload,
                "condition-valid_until": "2027-01-01",
            },
        )
        self.assertRedirects(
            response, reverse("employees:detail", args=[self.employee.pk])
        )
        self.previous.refresh_from_db()
        self.assertEqual(self.previous.valid_until, date(2026, 12, 1))
        self.assertEqual(self.previous.salary_amount_cents, 3000001)
        new = self.relationship.conditions.exclude(pk=self.previous.pk).get()
        self.assertEqual(new.salary_amount_cents, 3300002)
        self.assertEqual(str(new.working_time_percentage), "75.00")
        self.assertEqual(new.employee_insurance_exempt_cents, 4219)
        self.assertIsNone(new.valid_until)

    def test_splitting_closed_period_leaves_future_conditions_intact(self):
        self.previous.valid_until = date(2027, 1, 1)
        self.previous.save()
        future = create_record(
            EmploymentCondition,
            {
                **self.values,
                "valid_from": date(2027, 1, 1),
                "salary_amount_cents": 4000000,
            },
        )
        response = self.client.post(
            self.url, self.payload, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(
            response.headers["HX-Redirect"],
            reverse("employees:detail", args=[self.employee.pk]),
        )
        new = self.relationship.conditions.get(valid_from=date(2026, 12, 1))
        self.assertEqual(new.valid_until, date(2027, 1, 1))
        future.refresh_from_db()
        self.assertEqual(future.salary_amount_cents, 4000000)
        self.assertIsNone(future.valid_until)

    def test_invalid_change_dates_do_not_close_original(self):
        self.previous.valid_until = date(2027, 1, 1)
        self.previous.save()
        for value in ("2025-12-01", "2026-01-01", "2027-01-01", "2028-01-01"):
            with self.subTest(value=value):
                response = self.client.post(
                    self.url,
                    {
                        **self.payload,
                        "condition-valid_from": value,
                    },
                    HTTP_HX_REQUEST="true",
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    "valid_from", response.context["condition_form"].errors
                )
                self.assertNotContains(response, "<!doctype html>")
                self.previous.refresh_from_db()
                self.assertEqual(self.previous.valid_until, date(2027, 1, 1))
                self.assertEqual(EmploymentCondition.objects.count(), 1)

    def test_late_validation_failure_rolls_back_original_end(self):
        replacement = EmploymentCondition(
            **{
                **self.values,
                "valid_from": date(2026, 12, 1),
                "salary_amount_cents": -1,
            }
        )
        with self.assertRaises(ValidationError):
            change_conditions(self.previous, replacement)
        self.previous.refresh_from_db()
        self.assertIsNone(self.previous.valid_until)
        self.assertEqual(EmploymentCondition.objects.count(), 1)

    def test_add_conditions_after_empty_period_and_reject_overlap(self):
        self.previous.delete()
        url = reverse(
            "employees:condition-add",
            args=[self.employee.pk, self.relationship.pk],
        )
        response = self.client.post(url, self.payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.relationship.conditions.count(), 1)
        response = self.client.post(url, self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("valid_from", response.context["condition_form"].errors)
        self.assertEqual(self.relationship.conditions.count(), 1)

    def test_parent_lookup_staff_and_csrf_are_enforced(self):
        wrong = reverse(
            "employees:condition-change",
            args=[self.employee.pk + 999, self.previous.pk],
        )
        self.assertEqual(self.client.get(wrong).status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload).status_code, 403)
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(
            self.client.post(self.url, self.payload).status_code, 403
        )
        self.client.logout()
        self.assertIn(
            "HX-Redirect",
            self.client.get(self.url, HTTP_HX_REQUEST="true").headers,
        )
        self.previous.refresh_from_db()
        self.assertIsNone(self.previous.valid_until)
