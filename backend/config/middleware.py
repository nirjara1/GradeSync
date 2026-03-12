import logging
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from professor.models import UserProfile

logger = logging.getLogger(__name__)

class RoleBasedRoutingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        # ── Priority 1: Superuser / staff → ADMIN role ───────────────────────
        # Must be checked BEFORE looking up UserProfile, because superusers
        # created via `createsuperuser` typically have no UserProfile row.
        if request.user.is_superuser or request.user.is_staff:
            request.user_role = 'ADMIN'
            logger.info(
                "[Role Resolution Middleware] Authenticated User: %s | Resolved Role: ADMIN (superuser/staff)",
                request.user.username
            )
            # Admins may navigate anywhere — no route restrictions apply.
            return None

        # ── Priority 2-4: Role from UserProfile ──────────────────────────────
        try:
            profile = UserProfile.objects.get(user=request.user)
            role = profile.role
        except UserProfile.DoesNotExist:
            # Legacy fallback for 'poudelb2' or other profileless non-superusers
            if request.user.username == 'poudelb2':
                role = 'FACULTY'
            else:
                return None

        # Make role the single source of truth on the request object
        request.user_role = role
        logger.info(
            "[Role Resolution Middleware] Authenticated User: %s | Resolved Role: %s",
            request.user.username, role
        )

        path = request.path

        # Exclude auth, admin, and root paths from route-guard logic
        if (path.startswith('/accounts/')
                or path.startswith('/admin/')
                or path == '/'
                or path.startswith('/api/')):
            return None

        # Guard against redirect loops
        if hasattr(request, '_role_redirected'):
            return None

        # ── Route guards ──────────────────────────────────────────────────────
        if role == 'FACULTY':
            if path.startswith('/ga/') or path.startswith('/student/'):
                logger.info("[Route Guard] Blocked FACULTY from %s → /professor/dashboard/", path)
                request._role_redirected = True
                return redirect('/professor/dashboard/')

        elif role == 'GRADING_ASSISTANT':
            if path.startswith('/professor/') or path.startswith('/student/'):
                logger.info("[Route Guard] Blocked GRADING_ASSISTANT from %s → /ga/dashboard/", path)
                request._role_redirected = True
                return redirect('/ga/dashboard/')

        elif role == 'STUDENT':
            if path.startswith('/professor/') or path.startswith('/ga/'):
                logger.info("[Route Guard] Blocked STUDENT from %s → /student/dashboard/", path)
                request._role_redirected = True
                return redirect('/student/dashboard/')

        return None
