from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

import series.views as views

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", views.signup_view, name="signup"),
    path("accounts/settings/", views.account_settings_view, name="account-settings"),
    path("", include("series.urls")),
]
