from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    path("", views.home, name="home"),
    path("employees/", views.employee_list, name="list"),
    path("employees/new/", views.employee_registration, name="register"),
    path("employees/<int:pk>/", views.employee_detail, name="detail"),
    path("employees/<int:pk>/edit/", views.employee_edit, name="edit"),
]
