from django.core.management.base import BaseCommand
from django.db.models import Count
from shops.models import Shop


class Command(BaseCommand):
    help = 'Remove duplicate shops by keeping the first occurrence and deleting duplicates'

    def handle(self, *args, **options):
        # Find shops with duplicate names (case-insensitive)
        duplicate_names = Shop.objects.values('name').annotate(
            name_count=Count('id')
        ).filter(name_count__gt=1)

        total_removed = 0

        for dup in duplicate_names:
            name = dup['name']
            # Get all shops with this name, ordered by id (oldest first)
            shops = Shop.objects.filter(name__iexact=name).order_by('id')

            if shops.count() > 1:
                # Keep the first one, delete the rest
                keep_shop = shops.first()
                duplicates = shops.exclude(id=keep_shop.id)

                removed_count = duplicates.count()
                self.stdout.write(
                    f"Keeping shop '{name}' (ID: {keep_shop.id}), removing {removed_count} duplicate(s)"
                )

                duplicates.delete()
                total_removed += removed_count

        self.stdout.write(
            self.style.SUCCESS(f'Successfully removed {total_removed} duplicate shop(s)')
        )
