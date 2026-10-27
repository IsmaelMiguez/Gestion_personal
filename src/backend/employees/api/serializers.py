from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .. import services
from ..models import Company, Employee, EmploymentCondition, EmploymentRelationship


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
            "id", "internal_code", "first_name", "last_name", "birth_date", "tax_id",
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
    class Meta:
        model = EmploymentCondition
        fields = (
            "id", "employment_relationship", "valid_from", "valid_until",
            "contract_type", "working_time_percentage", "social_security_regime",
            "collective_agreement",
        )
