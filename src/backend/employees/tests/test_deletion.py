from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from ..services import create_record


class EmployeeDeletionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="delete-staff", is_staff=True
        )
        self.client.force_login(self.user)
        self.employee = create_record(
            Employee,
            {
                "internal_code": "DELETE-1",
                "first_name": "Alex",
                "last_name": "Example",
                "birth_date": date(1990, 1, 1),
            },
        )
        self.company = create_record(
            Company, {"name": "Example", "tax_id": "DELETE-COMPANY"}
        )
        self.relationship = create_record(
            EmploymentRelationship,
            {
                "employee": self.employee,
                "company": self.company,
                "start_date": date(2026, 1, 1),
                "end_date": None,
                "seniority_date": date(2020, 1, 1),
            },
        )
        self.condition = create_record(
            EmploymentCondition,
            {
                "employment_relationship": self.relationship,
                "valid_from": date(2026, 1, 1),
                "valid_until": date(2026, 7, 1),
                "contract_type": "Test",
                "working_time_percentage": "100",
                "social_security_regime": "Test",
                "collective_agreement": "Test",
            },
        )
        self.url = reverse("employees:delete", args=[self.employee.pk])
        self.condition_url = reverse(
            "employees:condition-delete",
            args=[self.employee.pk, self.condition.pk],
        )

    def test_confirmation_get_and_unconfirmed_post_never_delete(self):
        response = self.client.get(self.url)
        self.assertContains(response, "1 contrato")
        self.assertContains(response, "1 periodo")
        self.assertEqual(Employee.objects.count(), 1)
        for url in (self.url, self.condition_url):
            with self.subTest(url=url):
                response = self.client.post(url, {})
                self.assertEqual(response.status_code, 200)
                self.assertIn("confirm", response.context["form"].errors)
                self.assertEqual(Employee.objects.count(), 1)
                self.assertEqual(EmploymentCondition.objects.count(), 1)

    def test_employee_deletion_removes_dependents_and_keeps_company_and_other_staff(
        self,
    ):
        other = create_record(
            Employee,
            {
                "internal_code": "KEEP-1",
                "first_name": "Other",
                "last_name": "Example",
                "birth_date": date(1990, 1, 1),
            },
        )
        other_contract = create_record(
            EmploymentRelationship,
            {
                "employee": other,
                "company": self.company,
                "start_date": date(2026, 1, 1),
                "end_date": None,
                "seniority_date": date(2020, 1, 1),
            },
        )
        response = self.client.post(self.url, {"confirm": "on"})
        self.assertRedirects(response, reverse("employees:list"))
        self.assertFalse(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertFalse(
            EmploymentRelationship.objects.filter(
                pk=self.relationship.pk
            ).exists()
        )
        self.assertEqual(EmploymentCondition.objects.count(), 0)
        self.assertTrue(
            EmploymentRelationship.objects.filter(
                pk=other_contract.pk
            ).exists()
        )
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_condition_deletion_keeps_contract_and_does_not_extend_neighbors(
        self,
    ):
        following = create_record(
            EmploymentCondition,
            {
                "employment_relationship": self.relationship,
                "valid_from": date(2026, 7, 1),
                "valid_until": None,
                "contract_type": "Test",
                "working_time_percentage": "100",
                "social_security_regime": "Test",
                "collective_agreement": "Test",
            },
        )
        response = self.client.get(self.condition_url)
        self.assertContains(
            response, "puede quedar un intervalo sin condiciones"
        )
        response = self.client.post(
            self.condition_url, {"confirm": "on"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(
            response.headers["HX-Redirect"],
            reverse("employees:detail", args=[self.employee.pk]),
        )
        self.assertFalse(
            EmploymentCondition.objects.filter(pk=self.condition.pk).exists()
        )
        following.refresh_from_db()
        self.assertEqual(following.valid_from, date(2026, 7, 1))
        self.assertEqual(EmploymentRelationship.objects.count(), 1)
        self.assertEqual(Employee.objects.count(), 1)

    def test_protected_employee_deletion_rolls_back_earlier_child_deletions(
        self,
    ):
        with patch.object(
            Employee,
            "delete",
            side_effect=ProtectedError("protected", [self.employee]),
        ):
            response = self.client.post(self.url, {"confirm": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "otros registros vinculados")
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(EmploymentRelationship.objects.count(), 1)
        self.assertEqual(EmploymentCondition.objects.count(), 1)

    def test_deletion_requires_staff_csrf_and_matching_parent(self):
        wrong = reverse(
            "employees:condition-delete",
            args=[self.employee.pk + 999, self.condition.pk],
        )
        self.assertEqual(self.client.get(wrong).status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for url in (self.url, self.condition_url):
            with self.subTest(url=url):
                self.assertEqual(
                    client.post(url, {"confirm": "on"}).status_code, 403
                )
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(
            self.client.post(self.url, {"confirm": "on"}).status_code, 403
        )
        self.client.logout()
        self.assertEqual(
            self.client.post(self.url, {"confirm": "on"}).status_code, 302
        )
        self.assertEqual(Employee.objects.count(), 1)
