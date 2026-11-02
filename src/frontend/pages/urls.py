from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.entry, name="entry"),
    path("login/", views.ApplicationLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("documents/", views.documents, name="documents"),
]
