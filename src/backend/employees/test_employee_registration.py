from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from .services import create_record, register_employee


class EmployeeRegistrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="registration-staff", is_staff=True
        )
        self.client.force_login(self.user)
        self.company = create_record(
            Company,
            {
                "name": "Empresa de prueba",
                "tax_id": "SYNTHETIC-COMPANY",
            },
        )
        self.url = reverse("employees:register")
        self.payload = {
            "employee-internal_code": "EMP-NEW",
            "employee-first_name": "Alex",
            "employee-last_name": "Example",
            "employee-birth_date": "1990-01-01",
            "employee-identification_type": "PASSPORT",
            "employee-tax_id": "SYNTHETIC-DOCUMENT",
            "contract-company": str(self.company.pk),
            "contract-start_date": "2026-01-01",
            "contract-end_date": "",
            "contract-seniority_date": "2020-01-01",
            "condition-valid_from": "2026-01-01",
            "condition-valid_until": "",
            "condition-contract_type": "Indefinido",
            "condition-working_time_percentage": "100.00",
            "condition-social_security_regime": "Test",
            "condition-collective_agreement": "Test",
            "condition-job_title": "Administración",
            "condition-salary_amount": "2500.01",
            "condition-salary_period": "MONTHLY",
            "condition-payments_per_year": "14",
            "condition-fixed_supplement": "0.00",
            "condition-employee_insurance_exempt": "42.19",
            "condition-withholding_rate": "19.37",
        }

    def test_registration_renders_grouped_bootstrap_forms(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="registration-panel"')
        self.assertContains(response, "Empresa de prueba")
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'class="form-select"')
        self.assertEqual(
            response.context["condition_form"].initial["payments_per_year"], 14
        )
        self.assertNotIn(
            "employment_relationship",
            response.context["condition_form"].fields,
        )

    def test_registration_saves_linked_records_and_redirects(self):
        response = self.client.post(self.url, self.payload)
        employee = Employee.objects.get(internal_code="EMP-NEW")
        self.assertRedirects(
            response, reverse("employees:detail", args=[employee.pk])
        )
        relationship = EmploymentRelationship.objects.get(employee=employee)
        self.assertEqual(relationship.company, self.company)
        self.assertEqual(relationship.seniority_date, date(2020, 1, 1))
        condition = relationship.conditions.get()
        self.assertEqual(condition.salary_amount_cents, 250001)
        self.assertEqual(condition.employee_insurance_exempt_cents, 4219)
        self.assertEqual(condition.fixed_supplement_cents, 0)
        self.assertIsNone(condition.family_insurance_exempt_cents)
        self.assertEqual(condition.withholding_rate_basis_points, 1937)

    def test_htmx_success_redirects_to_full_detail(self):
        response = self.client.post(
            self.url, self.payload, HTTP_HX_REQUEST="true"
        )
        employee = Employee.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["HX-Redirect"],
            reverse("employees:detail", args=[employee.pk]),
        )

    def test_cross_form_error_rolls_back_and_preserves_input(self):
        payload = {**self.payload, "condition-valid_from": "2025-12-01"}
        response = self.client.post(self.url, payload, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "No se ha guardado el registro")
        self.assertContains(response, "Anterior al inicio")
        self.assertContains(response, 'value="Alex"')
        self.assertContains(response, 'value="2500.01"')
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(EmploymentRelationship.objects.count(), 0)
        self.assertEqual(EmploymentCondition.objects.count(), 0)
        self.assertEqual(Company.objects.count(), 1)

    def test_duplicate_employee_is_reported_without_extra_contract(self):
        self.client.post(self.url, self.payload)
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "internal_code", response.context["employee_form"].errors
        )
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(EmploymentRelationship.objects.count(), 1)
        self.assertEqual(EmploymentCondition.objects.count(), 1)

    def test_invalid_fields_do_not_write_any_registration(self):
        response = self.client.post(
            self.url,
            {
                **self.payload,
                "contract-company": str(self.company.pk + 999),
                "condition-withholding_rate": "100.01",
                "condition-salary_amount": "-1.00",
                "employee-first_name": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("first_name", response.context["employee_form"].errors)
        self.assertIn("company", response.context["relationship_form"].errors)
        self.assertIn(
            "salary_amount", response.context["condition_form"].errors
        )
        self.assertIn(
            "withholding_rate", response.context["condition_form"].errors
        )
        self.assertEqual(Employee.objects.count(), 0)

    def test_registration_without_company_explains_required_first_step(self):
        self.company.delete()
        response = self.client.get(self.url)
        self.assertContains(response, "crea su empresa")
        self.assertContains(response, 'type="submit" disabled')

    def test_registration_requires_staff_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Employee.objects.count(), 0)
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(
            self.client.post(self.url, self.payload).status_code, 403
        )
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_joint_service_rolls_back_late_model_validation_failure(self):
        employee = Employee(
            internal_code="SERVICE",
            first_name="Service",
            last_name="Example",
            birth_date=date(1990, 1, 1),
        )
        relationship = EmploymentRelationship(
            company=self.company,
            start_date=date(2026, 1, 1),
            seniority_date=date(2020, 1, 1),
        )
        condition = EmploymentCondition(
            valid_from=date(2026, 1, 1),
            contract_type="Test",
            working_time_percentage="101",
            social_security_regime="Test",
            collective_agreement="Test",
        )
        with self.assertRaises(ValidationError):
            register_employee(employee, relationship, condition)
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(EmploymentRelationship.objects.count(), 0)
        self.assertEqual(EmploymentCondition.objects.count(), 0)
