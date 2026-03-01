from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("items.urls")),
    path("professor/", include("professor.urls")),
    path("grading/", include("grading.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
]
