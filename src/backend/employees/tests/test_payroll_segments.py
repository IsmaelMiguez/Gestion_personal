from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from ..payroll_semester import annual_extra_estimate


class PayrollConditionSegmentTests(TestCase):
    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_user(
                username="segment-staff", is_staff=True
            )
        )
        company = Company.objects.create(
            name="Segment company", tax_id="SEGMENT"
        )
        employee = Employee.objects.create(
            internal_code="SEGMENT",
            first_name="Alex",
            last_name="Example",
            birth_date=date(1990, 1, 1),
        )
        self.relationship = EmploymentRelationship.objects.create(
            employee=employee,
            company=company,
            start_date=date(2026, 1, 1),
            seniority_date=date(2026, 1, 1),
        )
        values = dict(
            employment_relationship=self.relationship,
            contract_type="Indefinido",
            working_time_percentage=100,
            social_security_regime="General",
            collective_agreement="Prueba",
            contribution_group=5,
            occupational_risk_rate=Decimal("1.50"),
            salary_period="MONTHLY",
            payments_per_year=14,
            employee_insurance_exempt_cents=10000,
            employee_insurance_taxable_cents=0,
            family_insurance_exempt_cents=0,
            family_insurance_taxable_cents=0,
            withholding_rate_basis_points=1500,
        )
        self.first = EmploymentCondition.objects.create(
            **values,
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 1, 16),
            salary_amount_cents=200000,
            fixed_supplement_cents=10000,
        )
        values.update(employee_insurance_exempt_cents=20000)
        self.second = EmploymentCondition.objects.create(
            **values,
            valid_from=date(2026, 1, 16),
            salary_amount_cents=300000,
            fixed_supplement_cents=20000,
        )
        self.url = reverse("employees:calculation")
        self.payload = dict(
            companies=[company.pk],
            employees=[employee.pk],
            years=["2026"],
            months=["1"],
            columns=[
                "F",
                "O",
                "P",
                "Q",
                "U",
                "W",
                "X",
                "AC",
                "BV",
                "BY",
                "BZ",
                "CA",
                "CB",
            ],
            rounding=ROUND_HALF_UP,
            base_only="on",
        )

    def test_changes_sum_earnings_tax_and_insurance_with_one_monthly_contribution(
        self,
    ):
        response = self.client.post(self.url, self.payload)
        row = response.context["rows"][0]
        self.assertEqual(row["issues"], [])
        cells = {cell["code"]: cell for cell in row["cells"]}
        for code, expected in (
            ("O", "2500.00"),
            ("U", "150.00"),
            ("W", "2650.00"),
            ("Q", "150.00"),
            ("X", "493.06"),
            ("AC", "3143.06"),
            ("BZ", "397.50"),
            ("BV", "204.29"),
            ("CA", "1898.21"),
            ("CB", "3660.50"),
        ):
            with self.subTest(code=code):
                self.assertTrue(cells[code]["available"])
                self.assertEqual(cells[code]["value"], Decimal(expected))
        self.assertEqual(
            response.context["semester_extras"][0]["result"].amount,
            Decimal("2916.67"),
        )
        self.assertEqual(
            len(response.context["semester_extras"][0]["rows"]), 7
        )
        detail = self.client.post(
            self.url,
            {**self.payload, "cell": cells["O"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(detail, "Tramos de condiciones del mes")
        self.assertContains(detail, "16/01/2026")
        self.assertContains(detail, "1000.00 + 1500.00")
        self.assertNotContains(detail, "<!doctype html>")
        self.assertEqual(EmploymentCondition.objects.count(), 2)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.salary_amount_cents, 200000)
        self.assertEqual(self.second.salary_amount_cents, 300000)

    def test_minimum_is_checked_per_segment_but_maximum_is_monthly(self):
        for condition, salary in ((self.first, 10000), (self.second, 300000)):
            condition.salary_amount_cents = salary
            condition.payments_per_year = 12
            condition.fixed_supplement_cents = 0
            condition.employee_insurance_exempt_cents = 0
            condition.save()
        response = self.client.post(self.url, self.payload)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["W"]["value"], Decimal(1550))
        self.assertEqual(cells["AC"]["value"], Decimal("2212.20"))
        self.first.salary_amount_cents = 1000000
        self.second.salary_amount_cents = 600000
        self.first.save()
        self.second.save()
        response = self.client.post(self.url, self.payload)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["W"]["value"], Decimal(8000))
        self.assertEqual(cells["AC"]["value"], Decimal("5101.20"))

    def test_day_31_does_not_duplicate_salary_or_extra_accrual(self):
        self.first.valid_until = date(2026, 1, 31)
        self.second.valid_from = date(2026, 1, 31)
        self.first.save()
        self.second.save()
        response = self.client.post(self.url, self.payload)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["O"]["value"], Decimal(2000))
        segments = cells["O"]["condition_segments"]
        self.assertEqual(
            [segment["salary_days"] for segment in segments], [30, 0]
        )
        self.assertEqual(
            [segment["contribution_days"] for segment in segments], [30, 0]
        )
        self.assertEqual(
            response.context["semester_extras"][0]["result"].amount,
            Decimal("2833.33"),
        )

    def test_february_and_partial_hire_partition_the_existing_standard_month(
        self,
    ):
        self.relationship.start_date = date(2026, 2, 15)
        self.relationship.save()
        self.first.valid_from = date(2026, 2, 15)
        self.first.valid_until = date(2026, 2, 21)
        self.second.valid_from = date(2026, 2, 21)
        self.first.save()
        self.second.save()
        response = self.client.post(
            self.url, {**self.payload, "months": ["2"]}
        )
        row = response.context["rows"][0]
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertEqual(cells["O"]["value"], Decimal(1400))
        self.assertEqual(
            [
                segment["salary_days"]
                for segment in cells["O"]["condition_segments"]
            ],
            [6, 10],
        )
        self.assertEqual(
            [
                segment["contribution_days"]
                for segment in cells["O"]["condition_segments"]
            ],
            [6, 8],
        )
        self.assertTrue(cells["CA"]["available"])
        self.assertEqual(
            response.context["semester_extras"][0]["result"].amount,
            Decimal("2233.33"),
        )

    def test_gaps_overlaps_and_unknown_data_do_not_publish_partial_totals(
        self,
    ):
        for start in (date(2026, 1, 17), date(2026, 1, 15)):
            self.second.valid_from = start
            self.second.save()
            response = self.client.post(self.url, self.payload)
            cells = {
                cell["code"]: cell
                for cell in response.context["rows"][0]["cells"]
            }
            self.assertFalse(cells["O"]["available"])
            self.assertFalse(cells["CA"]["available"])
            self.assertIsNone(response.context["semester_extras"][0]["result"])
        self.second.valid_from = date(2026, 1, 16)
        self.second.fixed_supplement_cents = None
        self.second.save()
        response = self.client.post(self.url, self.payload)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertTrue(cells["O"]["available"])
        self.assertFalse(cells["W"]["available"])
        self.assertFalse(cells["CA"]["available"])

    def test_unresolved_contribution_changes_and_payment_modes_remain_explicit(
        self,
    ):
        self.second.contribution_group = 1
        self.second.save()
        response = self.client.post(self.url, self.payload)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertTrue(cells["W"]["available"])
        self.assertFalse(cells["AC"]["available"])
        self.assertIn("grupo de cotización", cells["AC"]["note"])
        self.second.contribution_group = 5
        self.second.payments_per_year = 12
        self.second.save()
        estimate = annual_extra_estimate(
            self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 26)
        )
        self.assertIsNone(estimate["amount"])
        self.assertTrue(
            any("12 y 14" in issue for issue in estimate["issues"])
        )

    def test_changed_withholding_rate_preserves_contributions_but_waits_for_payment_details(
        self,
    ):
        self.second.withholding_rate_basis_points = 2000
        self.second.save()
        response = self.client.post(self.url, self.payload)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertTrue(cells["AC"]["available"])
        self.assertFalse(cells["BZ"]["available"])
        self.assertFalse(cells["CA"]["available"])
        self.assertIn("fecha de pago", cells["BZ"]["note"])

    def test_anniversary_month_uses_each_segments_monthly_seniority_base_once(
        self,
    ):
        self.relationship.seniority_date = date(2024, 1, 15)
        self.relationship.save()
        response = self.client.post(self.url, self.payload)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["P"]["value"], Decimal("132.50"))
        segments = cells["P"]["condition_segments"]
        self.assertEqual(segments[0]["values"]["P"], Decimal("52.50"))
        self.assertEqual(segments[1]["values"]["P"], Decimal("80.00"))
        self.assertEqual(
            response.context["semester_extras"][0]["result"].amount,
            Decimal("3072.08"),
        )

    def test_partial_time_segments_do_not_guess_hours_from_the_monthly_total(
        self,
    ):
        self.first.working_time_percentage = 50
        self.second.working_time_percentage = 50
        self.first.save()
        self.second.save()
        response = self.client.post(
            self.url,
            {
                **self.payload,
                f"hours-{self.relationship.pk}-2026-1-worked_hours": "80",
            },
        )
        row = response.context["rows"][0]
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertEqual(cells["O"]["value"], Decimal(2500))
        self.assertFalse(cells["AC"]["available"])
        self.assertIn("horas reales de cada tramo", cells["AC"]["note"])
        self.assertFalse(row["requires_hours"])
