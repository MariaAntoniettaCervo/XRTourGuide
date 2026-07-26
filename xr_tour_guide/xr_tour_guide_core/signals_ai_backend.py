from django.db import transaction
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


@receiver(post_save, sender=Waypoint)
def waypoint_saved_commit_pending_audio(sender, instance, **kwargs):
    """
    Rete di sicurezza: se l'utente ha generato un'anteprima audio ma non l'ha
    scartata esplicitamente, e nel frattempo salva comunque il Waypoint (il
    "Salva" generale del form), l'anteprima pendente viene confermata qui —
    così non si perde mai un audio generato solo perché ci si è dimenticati
    di scartarlo esplicitamente.

    Importante: il lavoro vero (scrittura su MinIO) NON avviene qui dentro,
    per due motivi:
    1. Questo signal gira ancora dentro la stessa transazione atomica con cui
       nested_admin salva l'intero formset annidato — un problema lì dentro
       romperebbe l'intera transazione esterna (transaction.on_commit rimanda
       comunque l'esecuzione a dopo che la transazione è confermata).
    2. Anche dopo la conferma della transazione, il processo Django in quel
       momento ha una pila di chiamate già molto profonda (admin, formset
       nested, mixin di unfold) — scrivere su MinIO lì dentro può superare il
       limite di ricorsione di Python. Per questo l'operazione vera è
       accodata come task Celery (xr_tour_guide.tasks.commit_pending_audio_task),
       che gira in un processo separato con una pila di chiamate fresca.
    """
    from xr_tour_guide.tasks import commit_pending_audio_task

    waypoint_id = instance.pk
    transaction.on_commit(
        lambda: commit_pending_audio_task.apply_async(args=[waypoint_id], queue='api_tasks')
    )