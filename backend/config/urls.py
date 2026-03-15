from django.urls import path, include
from django.views.generic import RedirectView
from professor import views as professor_views
from items.admin import gradesync_admin

urlpatterns = [
    path("admin/login/", RedirectView.as_view(url="/accounts/login/")),
    path("admin/", gradesync_admin.urls),
    path("", include("items.urls")),
    path("professor/", include("professor.urls")),
    path("ga/", include("professor.ga_urls")),
    path("student/", include("portal.urls")),
    path("grading/", include("grading.urls")),
    path("accounts/register/", professor_views.register_view, name="register"),
    path("accounts/login/", professor_views.CustomLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
]

from django.conf import settings
from django.urls import re_path
from django.views.static import serve
from django.http import HttpResponseForbidden

def protected_media_serve(request, path, document_root=None, show_indexes=False):
    # Protect test data downloads: only staff, faculty, or grading assistants can download them
    if 'test_data/' in path or 'expected_outputs/' in path:
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return HttpResponseForbidden("Not authorized.")
            
        if not (getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
            try:
                profile = getattr(user, 'profile', None)
                if profile and getattr(profile, 'role', None) == 'STUDENT':
                    return HttpResponseForbidden("Students are not allowed to download test data.")
            except Exception:
                return HttpResponseForbidden("Not authorized.")
                
    return serve(request, path, document_root, show_indexes)

if settings.DEBUG or True: # Force for local dev
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', protected_media_serve, {'document_root': settings.MEDIA_ROOT}),
    ]

