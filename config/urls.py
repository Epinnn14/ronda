from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("masuk/", auth_views.LoginView.as_view(), name="login"),
    path("keluar/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("rt.urls")),
]
