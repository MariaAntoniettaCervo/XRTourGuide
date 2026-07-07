from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from xr_tour_guide_core.services.tour_portability import (
    TourPortabilityService,
    TourPortabilityError,
)


class Command(BaseCommand):
    help = "Import a tour from a ZIP archive"

    def add_arguments(self, parser):
        parser.add_argument("archive", type=str)
        parser.add_argument("--owner", type=str, required=False)
        parser.add_argument("--no-copy", action="store_true")

    def handle(self, *args, **options):
        owner = None
        if options.get("owner"):
            User = get_user_model()
            try:
                owner = User.objects.get(username=options["owner"])
            except User.DoesNotExist:
                raise CommandError("Owner user not found")

        service = TourPortabilityService()

        try:
            with open(options["archive"], "rb") as f:
                tour = service.import_tour(
                    archive_file=f,
                    owner=owner,
                    create_copy=not options["no_copy"],
                )
        except FileNotFoundError:
            raise CommandError("Archive file not found")
        except TourPortabilityError as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(f"Imported tour #{tour.pk} - {tour.title}"))