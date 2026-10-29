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

    def test_identification_type_choices_and_value_are_preserved(self):
        for identification_type in Employee.IdentificationType.values:
            with self.subTest(identification_type=identification_type):
                response = self.client.patch(
                    f"/api/employees/{self.employee.pk}/",
                    {
                        "identification_type": identification_type,
                        "tax_id": "SYNTHETIC-001",
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 200, response.data)
                self.employee.refresh_from_db()
                self.assertEqual(
                    self.employee.identification_type, identification_type
                )
                self.assertEqual(self.employee.tax_id, "SYNTHETIC-001")

    def test_unknown_identification_type_is_rejected(self):
        response = self.client.patch(
            f"/api/employees/{self.employee.pk}/",
            {"identification_type": "UNKNOWN"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("identification_type", response.data)

    def test_retribution_api_round_trip_is_exact_and_partial_updates_preserve_it(self):
        payload = {
            **self.values,
            "employment_relationship": self.relationship.pk,
            "job_title": "Administración",
            "salary_amount": "30000.01",
            "salary_period": "ANNUAL",
            "payments_per_year": 14,
            "employee_insurance_exempt": "42.19",
            "employee_insurance_taxable": "55.01",
            "family_insurance_exempt": "126.56",
            "family_insurance_taxable": "165.03",
            "fixed_supplement": "0.10",
            "withholding_rate": "19.37",
        }
        response = self.client.post(
            "/api/employment-conditions/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        condition = EmploymentCondition.objects.get(pk=response.data["id"])
        self.assertEqual(condition.salary_amount_cents, 3000001)
        self.assertEqual(condition.withholding_rate_basis_points, 1937)
        for name in (
            "salary_amount", "employee_insurance_exempt",
            "employee_insurance_taxable", "family_insurance_exempt",
            "family_insurance_taxable", "fixed_supplement", "withholding_rate",
        ):
            self.assertEqual(response.data[name], payload[name])
        response = self.client.patch(
            f"/api/employment-conditions/{condition.pk}/",
            {"job_title": "Responsable de administración"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["salary_amount"], "30000.01")

    def test_salary_requires_explicit_unit_and_number_of_payments(self):
        condition = create_record(EmploymentCondition, self.values)
        url = f"/api/employment-conditions/{condition.pk}/"
        response = self.client.patch(
            url, {"salary_amount": "2500.00"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("salary_period", response.data)
        self.assertIn("payments_per_year", response.data)
        condition.refresh_from_db()
        self.assertIsNone(condition.salary_amount_cents)
        response = self.client.patch(
            url, {"salary_period": "MONTHLY"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_retribution_inputs_are_rejected(self):
        condition = create_record(EmploymentCondition, self.values)
        url = f"/api/employment-conditions/{condition.pk}/"
        cases = (
            {"fixed_supplement": "-0.01"},
            {"employee_insurance_exempt": "0.001"},
            {"withholding_rate": "100.01"},
            {"payments_per_year": 13},
            {"salary_period": "WEEKLY"},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.patch(url, payload, format="json")
                self.assertEqual(response.status_code, 400, response.data)

    def test_missing_amount_and_explicit_zero_are_distinct(self):
        condition = create_record(EmploymentCondition, self.values)
        self.assertIsNone(condition.fixed_supplement_cents)
        response = self.client.patch(
            f"/api/employment-conditions/{condition.pk}/",
            {"fixed_supplement": "0.00"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["fixed_supplement"], "0.00")
        self.assertIsNone(response.data["employee_insurance_exempt"])

    def test_new_salary_period_does_not_overwrite_previous_salary(self):
        first = create_record(EmploymentCondition, {
            **self.values, "salary_amount_cents": 3000000,
            "salary_period": "ANNUAL", "payments_per_year": 14,
        })
        create_record(EmploymentCondition, {
            **self.values, "valid_from": date(2026, 7, 1),
            "valid_until": None, "salary_amount_cents": 3300000,
            "salary_period": "ANNUAL", "payments_per_year": 12,
        })
        first.refresh_from_db()
        self.assertEqual(first.salary_amount_cents, 3000000)
        self.assertEqual(first.payments_per_year, 14)

    def test_admin_form_creates_and_updates_euro_amounts(self):
        from django.contrib import admin
        from django.test import RequestFactory

        model_admin = admin.site._registry[EmploymentCondition]
        request = RequestFactory().get("/admin/employees/employmentcondition/add/")
        request.user = get_user_model().objects.create_superuser(
            username="admin-test", password="Test-only-strong-password-123"
        )
        form_class = model_admin.get_form(request)
        payload = {
            **self.values, "employment_relationship": self.relationship.pk,
            "salary_amount": "2500.01", "salary_period": "MONTHLY",
            "payments_per_year": 14, "withholding_rate": "15.25",
            "fixed_supplement": "10.10",
        }
        form = form_class(data=payload)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        model_admin.save_model(request, instance, form, False)
        self.assertEqual(instance.salary_amount_cents, 250001)
        self.assertEqual(instance.withholding_rate_basis_points, 1525)
        payload["salary_amount"] = "2600.02"
        form = model_admin.get_form(request, instance)(
            data=payload, instance=instance
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        model_admin.save_model(request, instance, form, True)
        instance.refresh_from_db()
        self.assertEqual(instance.salary_amount_cents, 260002)
        self.assertEqual(instance.fixed_supplement_cents, 1010)

    def test_database_rejects_invalid_payment_count(self):
        from django.db import IntegrityError, transaction

        condition = create_record(EmploymentCondition, self.values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmploymentCondition.objects.filter(pk=condition.pk).update(
                payments_per_year=13
            )
