from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xr_tour_guide.settings')

app = Celery('xr_tour_guide')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks(lambda: ['xr_tour_guide'])

app.conf.task_queues = {
    'api_tasks': {
        'exchange': 'api_tasks',
        'routing_key': 'api_tasks',
    }
}

app.conf.beat_schedule = {
    'fail-stuck-builds': {
        'task': 'xr_tour_guide.tasks.fail_stuck_builds',
        'schedule': timedelta(seconds=40),
    },
    'remove_append_user': {
        'task': 'xr_tour_guide.tasks.remove_append_user',
        'schedule': timedelta(minutes=5),
    },
    'remove_sub_tours': {
        'task': 'xr_tour_guide.tasks.remove_sub_tours',
        'schedule': timedelta(minutes=30),
    },
    'clear-ai-inference-cache-daily': {
        'task': 'xr_tour_guide.tasks.clear_ai_inference_cache',
        'schedule': 24 * 60 * 60,
    }
}