from django.urls import path, include
from items.admin import gradesync_admin

urlpatterns = [
    path("admin/", gradesync_admin.urls),
    path("", include("items.urls")),
]
