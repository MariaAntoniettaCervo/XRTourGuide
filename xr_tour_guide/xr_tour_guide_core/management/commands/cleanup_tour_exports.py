import time
from pathlib import Path
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Remove old exported tour ZIP files"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        export_dir = Path("/tmp/xr_tour_exports")
        if not export_dir.exists():
            self.stdout.write("No export directory found")
            return

        threshold = time.time() - (options["hours"] * 3600)
        removed = 0

        for file_path in export_dir.glob("*.zip"):
            try:
                if file_path.stat().st_mtime < threshold:
                    file_path.unlink()
                    removed += 1
            except FileNotFoundError:
                pass

        self.stdout.write(self.style.SUCCESS(f"Removed {removed} old export files"))