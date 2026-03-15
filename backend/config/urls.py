from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth.decorators import login_required
from professor import views as professor_views
from items.admin import gradesync_admin
from portal import views as portal_views

urlpatterns = [
    path("admin/login/", RedirectView.as_view(url="/accounts/login/")),
    path("admin/", gradesync_admin.urls),
    path("", include("items.urls")),
    path("professor/", include("professor.urls")),
    path("ga/", include("professor.ga_urls")),
    path("student/", include("portal.urls")),
    path("grading/", include("grading.urls")),
    path("profile/", login_required(portal_views.user_profile_view), name="user_profile"),
    path("accounts/register/", professor_views.register_view, name="register"),
    path("accounts/login/", professor_views.CustomLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG or True: # Force for local dev
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

