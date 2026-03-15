import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('gradesync')

# Load configuration from Django settings, all config keys will be namespaced with `CELERY_`
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered Django apps
app.autodiscover_tasks()

# Optional: Define periodic tasks
app.conf.beat_schedule = {
    # Example: clean up old task results every hour
    'cleanup-old-results': {
        'task': 'grading.tasks.cleanup_old_results',
        'schedule': crontab(minute=0),  # Run at the start of every hour
    },
}

# Configure task settings
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    result_expires=3600,  # Results expire after 1 hour
)

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery configuration"""
    print(f'Request: {self.request!r}')
