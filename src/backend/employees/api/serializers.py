from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .. import services
from ..models import Company, Employee, EmploymentCondition, EmploymentRelationship


class HundredthsField(serializers.DecimalField):
    """Convert decimal display values to integer hundredths and back."""

    def __init__(self, **kwargs):
        super().__init__(
            max_digits=12, decimal_places=2, min_value=Decimal("0"),
            allow_null=True, required=False, coerce_to_string=True, **kwargs,
        )

    def run_validation(self, data):
        value = super().run_validation(data)
        return int(value * 100) if value is not None else None

    def to_representation(self, value):
        return super().to_representation(Decimal(value) / 100)


class ValidatedModelSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            return services.create_record(self.Meta.model, validated_data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error

    def update(self, instance, validated_data):
        try:
            return services.update_record(instance, validated_data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error


class EmployeeSerializer(ValidatedModelSerializer):
    class Meta:
        model = Employee
        fields = (
            "id", "internal_code", "first_name", "last_name", "birth_date",
            "identification_type", "tax_id",
        )


class CompanySerializer(ValidatedModelSerializer):
    class Meta:
        model = Company
        fields = ("id", "name", "tax_id")


class EmploymentRelationshipSerializer(ValidatedModelSerializer):
    class Meta:
        model = EmploymentRelationship
        fields = (
            "id", "employee", "company", "start_date", "end_date", "seniority_date",
        )


class EmploymentConditionSerializer(ValidatedModelSerializer):
    salary_amount = HundredthsField(source="salary_amount_cents")
    employee_insurance_exempt = HundredthsField(
        source="employee_insurance_exempt_cents"
    )
    employee_insurance_taxable = HundredthsField(
        source="employee_insurance_taxable_cents"
    )
    family_insurance_exempt = HundredthsField(
        source="family_insurance_exempt_cents"
    )
    family_insurance_taxable = HundredthsField(
        source="family_insurance_taxable_cents"
    )
    fixed_supplement = HundredthsField(source="fixed_supplement_cents")
    withholding_rate = HundredthsField(
        source="withholding_rate_basis_points", max_value=Decimal("100")
    )

    class Meta:
        model = EmploymentCondition
        fields = (
            "id", "employment_relationship", "valid_from", "valid_until",
            "contract_type", "working_time_percentage", "social_security_regime",
            "collective_agreement", "job_title", "salary_amount",
            "salary_period", "payments_per_year", "employee_insurance_exempt",
            "employee_insurance_taxable", "family_insurance_exempt",
            "family_insurance_taxable", "fixed_supplement", "withholding_rate",
        )
