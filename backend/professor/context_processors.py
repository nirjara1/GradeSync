def display_username_processor(request):
    """
    Prefer the user's registered full name (User.first_name + last_name).
    Falls back to email local-part or username for legacy accounts without names.
    """
    if request.user.is_authenticated:
        user = request.user
        full = (user.get_full_name() or '').strip()
        if full:
            display_name = full
        else:
            email = (user.email or '').strip()
            if email and '@' in email:
                local = email.split('@')[0].replace('.', ' ').replace('_', ' ')
                display_name = local.title() if local else user.username
            else:
                display_name = user.username.replace('.', ' ').title()
    else:
        display_name = 'Guest'

    return {'display_name': display_name}
