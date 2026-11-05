from django.urls import path

from . import condition_views, deletion_views, payroll_views, views

app_name = "employees"

urlpatterns = [
    path("", views.home, name="home"),
    path("simulation/", payroll_views.ordinary_payroll, name="simulation"),
    path("employees/", views.employee_list, name="list"),
    path("employees/new/", views.employee_registration, name="register"),
    path("employees/<int:pk>/", views.employee_detail, name="detail"),
    path("employees/<int:pk>/edit/", views.employee_edit, name="edit"),
    path(
        "employees/<int:pk>/delete/",
        deletion_views.employee_delete,
        name="delete",
    ),
    path(
        "employees/<int:employee_pk>/relationships/<int:relationship_pk>/conditions/new/",
        condition_views.condition_add,
        name="condition-add",
    ),
    path(
        "employees/<int:employee_pk>/conditions/<int:pk>/change/",
        condition_views.condition_change,
        name="condition-change",
    ),
    path(
        "employees/<int:employee_pk>/conditions/<int:pk>/delete/",
        deletion_views.condition_delete,
        name="condition-delete",
    ),
]
