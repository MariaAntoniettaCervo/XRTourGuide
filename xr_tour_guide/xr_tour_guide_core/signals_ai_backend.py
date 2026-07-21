from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Tour, Waypoint
from xr_tour_guide.tasks import compute_chunks_task


@receiver(post_save, sender=Tour)
def tour_saved_compute_chunks(sender, instance, **kwargs):
    if instance.description and instance.description.strip():
        compute_chunks_task.apply_async(args=[instance.description], queue='api_tasks')


@receiver(post_save, sender=Waypoint)
def waypoint_saved_compute_chunks(sender, instance, **kwargs):
    if instance.description and instance.description.strip():
        compute_chunks_task.apply_async(args=[instance.description], queue='api_tasks')