# This will make sure the app is always imported when Django starts.
# Celery is optional: if not installed (e.g. local dev), Django still runs.
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ModuleNotFoundError:
    celery_app = None
    __all__ = ()
