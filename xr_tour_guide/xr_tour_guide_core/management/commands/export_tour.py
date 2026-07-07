from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from xr_tour_guide_core.models import Tour
from xr_tour_guide_core.services.tour_portability import TourPortabilityService


class Command(BaseCommand):
    help = "Export a tour to a ZIP archive"

    def add_arguments(self, parser):
        parser.add_argument("tour_id", type=int)
        parser.add_argument("--output", type=str, required=False)
        parser.add_argument("--without-subtours", action="store_true")

    def handle(self, *args, **options):
        try:
            tour = Tour.objects.get(pk=options["tour_id"])
        except Tour.DoesNotExist:
            raise CommandError("Tour not found")

        service = TourPortabilityService()
        output = options.get("output")
        archive_path = service.export_tour(
            tour,
            include_subtours=not options["without_subtours"],
            output_path=output,
        )

        self.stdout.write(self.style.SUCCESS(f"Exported to {archive_path}"))