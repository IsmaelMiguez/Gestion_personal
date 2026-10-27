from rest_framework.routers import DefaultRouter

from .views import (
    CompanyViewSet, EmployeeViewSet, EmploymentConditionViewSet,
    EmploymentRelationshipViewSet,
)

router = DefaultRouter()
router.register("employees", EmployeeViewSet)
router.register("companies", CompanyViewSet)
router.register("employment-relationships", EmploymentRelationshipViewSet)
router.register("employment-conditions", EmploymentConditionViewSet)

urlpatterns = router.urls
