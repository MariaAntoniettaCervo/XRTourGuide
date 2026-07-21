from django.db.models import Q
from xr_tour_guide_core.models import TourCollaboratorRole


def can_view_tour(user, tour):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if tour is None:
        return False

    if tour.user_id == user.id:
        return True

    if not tour.pk:
        return False

    return tour.collaborators.filter(user=user).exists()


def can_edit_tour(user, tour):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if tour is None:
        return False

    if tour.user_id == user.id:
        return True

    if not tour.pk:
        return False

    return tour.collaborators.filter(
        user=user,
        role=TourCollaboratorRole.EDITOR,
    ).exists()


def visible_tours_queryset(user, queryset):
    if not user or not user.is_authenticated:
        return queryset.none()

    if user.is_superuser:
        return queryset

    return queryset.filter(
        Q(user=user) |
        Q(collaborators__user=user)
    ).distinct()


def can_delete_tour(user, tour):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if tour is None:
        return False

    return tour.user_id == user.id


def can_manage_tour_collaborators(user, tour):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if tour is None:
        return False

    # Durante la creazione il Tour non è ancora salvato e user è ancora None.
    # L'utente corrente diventerà proprietario in TourAdmin.save_model().
    if not tour.pk and tour.user_id is None:
        return True

    return tour.user_id == user.id
