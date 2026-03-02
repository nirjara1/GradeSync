import logging
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from professor.models import UserProfile

logger = logging.getLogger(__name__)

class RoleBasedRoutingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.user.is_authenticated:
            return None
            
        try:
            profile = UserProfile.objects.get(user=request.user)
            role = profile.role
        except UserProfile.DoesNotExist:
            if request.user.username == 'poudelb2' or request.user.is_superuser:
                role = 'FACULTY'
            else:
                return None
                
        # Make role the single source of truth in backend (accessible directly on request)
        request.user_role = role
        logger.info(f"[Role Resolution Middleware] Authenticated User: {request.user.username} | Resolved Role: {role}")
        
        path = request.path
        
        # Exclude administrative or auth paths
        if path.startswith('/accounts/') or path.startswith('/admin/') or path == '/' or path.startswith('/api/'):
            return None
            
        # Add an attribute to avoid redirect loops
        if hasattr(request, '_role_redirected'):
            return None
            
        # Role-based constraints
        if role == 'FACULTY':
            if path.startswith('/ga/') or path.startswith('/student/'):
                logger.info(f"[Route Guard] Blocked PROFESSOR opening {path}, redirecting to /professor/dashboard/")
                request._role_redirected = True
                return redirect('/professor/dashboard/')
        elif role == 'GRADING_ASSISTANT':
            if path.startswith('/professor/') or path.startswith('/student/'):
                logger.info(f"[Route Guard] Blocked GRADING_ASSISTANT opening {path}, redirecting to /ga/dashboard/")
                request._role_redirected = True
                return redirect('/ga/dashboard/')
        elif role == 'STUDENT':
            if path.startswith('/professor/') or path.startswith('/ga/'):
                logger.info(f"[Route Guard] Blocked STUDENT opening {path}, redirecting to /student/dashboard/")
                request._role_redirected = True
                return redirect('/student/dashboard/')
        
        return None
