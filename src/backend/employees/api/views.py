from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAdminUser

from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from .serializers import (
    CompanySerializer,
    EmployeeSerializer,
    EmploymentConditionSerializer,
    EmploymentRelationshipSerializer,
)


class RegistrationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAdminUser]


class EmployeeViewSet(RegistrationViewSet):
    queryset = Employee.objects.order_by("internal_code")
    serializer_class = EmployeeSerializer


class CompanyViewSet(RegistrationViewSet):
    queryset = Company.objects.order_by("name", "pk")
    serializer_class = CompanySerializer


class EmploymentRelationshipViewSet(RegistrationViewSet):
    queryset = EmploymentRelationship.objects.select_related(
        "employee", "company"
    ).order_by("pk")
    serializer_class = EmploymentRelationshipSerializer


class EmploymentConditionViewSet(RegistrationViewSet):
    queryset = EmploymentCondition.objects.select_related(
        "employment_relationship"
    ).order_by("pk")
    serializer_class = EmploymentConditionSerializer
