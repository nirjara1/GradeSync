from django.contrib.auth.models import User

def display_username_processor(request):
    if request.user.is_authenticated:
        email = request.user.email
        if email:
            # Extract the part before '@' and capitalize
            display_name = email.split('@')[0].capitalize()
        else:
            # Fallback to username and capitalize
            display_name = request.user.username.capitalize()
    else:
        # Fallback for unauthenticated or prototype previewing
        display_name = "Guest"
    
    return {
        'display_name': display_name
    }
