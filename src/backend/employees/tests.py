from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Company, Employee, EmploymentCondition, EmploymentRelationship
from .services import create_record, update_record


class EmploymentRegistrationTests(TestCase):
    def setUp(self):
        self.employee = create_record(Employee, {
            "internal_code": "EMP-001", "first_name": "Alex", "last_name": "Example",
            "birth_date": date(1990, 1, 1), "tax_id": "",
        })
        self.company = create_record(Company, {"name": "Example", "tax_id": "TEST-001"})
        self.relationship = create_record(EmploymentRelationship, {
            "employee": self.employee, "company": self.company,
            "start_date": date(2026, 1, 1), "end_date": None,
            "seniority_date": date(2020, 1, 1),
        })
        self.values = {
            "employment_relationship": self.relationship,
            "valid_from": date(2026, 1, 1), "valid_until": date(2026, 7, 1),
            "contract_type": "Indefinido", "working_time_percentage": Decimal("50"),
            "social_security_regime": "Pendiente de clasificación",
            "collective_agreement": "Convenio de prueba",
        }
        self.client = APIClient()
        user = get_user_model().objects.create_user(username="tester", is_staff=True)
        self.client.force_authenticate(user=user)

    def test_adjacent_conditions_preserve_history(self):
        first = create_record(EmploymentCondition, self.values)
        second = create_record(EmploymentCondition, {
            **self.values, "valid_from": date(2026, 7, 1),
            "valid_until": None, "working_time_percentage": Decimal("100"),
        })
        self.assertEqual(self.relationship.conditions.count(), 2)
        first.refresh_from_db()
        self.assertEqual(first.working_time_percentage, Decimal("50"))
        self.assertEqual(second.working_time_percentage, Decimal("100"))

    def test_overlapping_condition_is_rejected_without_writing(self):
        create_record(EmploymentCondition, self.values)
        with self.assertRaises(ValidationError):
            create_record(EmploymentCondition, {**self.values, "valid_until": None})
        self.assertEqual(self.relationship.conditions.count(), 1)

    def test_invalid_percentages_are_rejected(self):
        for percentage in ("0", "-1", "100.01"):
            with self.subTest(percentage=percentage), self.assertRaises(ValidationError):
                create_record(EmploymentCondition, {
                    **self.values, "working_time_percentage": Decimal(percentage),
                })

    def test_condition_must_fit_relationship(self):
        with self.assertRaises(ValidationError):
            create_record(EmploymentCondition, {
                **self.values, "valid_from": date(2025, 12, 31),
            })
        update_record(self.relationship, {"end_date": date(2026, 6, 1)})
        with self.assertRaises(ValidationError):
            create_record(EmploymentCondition, self.values)

    def test_reversed_interval_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_record(EmploymentCondition, {
                **self.values, "valid_until": self.values["valid_from"],
            })

    def test_shortening_relationship_cannot_orphan_conditions(self):
        create_record(EmploymentCondition, self.values)
        with self.assertRaises(ValidationError):
            update_record(self.relationship, {"end_date": date(2026, 3, 1)})
        self.relationship.refresh_from_db()
        self.assertIsNone(self.relationship.end_date)

    def test_api_registration_and_partial_update(self):
        payload = {**self.values, "employment_relationship": self.relationship.pk}
        response = self.client.post("/api/employment-conditions/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.patch(
            f'/api/employment-conditions/{response.data["id"]}/',
            {"working_time_percentage": "75.00"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["working_time_percentage"], "75.00")

    def test_api_reports_domain_validation(self):
        create_record(EmploymentCondition, self.values)
        payload = {**self.values, "employment_relationship": self.relationship.pk}
        response = self.client.post("/api/employment-conditions/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid_from", response.data)

    def test_api_rejects_unknown_relationship(self):
        payload = {**self.values, "employment_relationship": self.relationship.pk + 999}
        response = self.client.post("/api/employment-conditions/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_api_requires_staff_access(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/employees/").status_code, 403)
        user = get_user_model().objects.create_user(username="ordinary")
        self.client.force_authenticate(user=user)
        self.assertEqual(self.client.get("/api/employees/").status_code, 403)

    def test_api_rejects_duplicate_employee_code(self):
        response = self.client.post("/api/employees/", {
            "internal_code": "EMP-001", "first_name": "Other", "last_name": "Person",
            "birth_date": "1991-01-01", "tax_id": "",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Employee.objects.count(), 1)
