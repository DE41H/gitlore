from django.db.models.signals import post_save
from django.db.transaction import on_commit
from django.dispatch import receiver

from series.models import Chapter, Character, Series, World
from series.tasks import (
    create_character_embeddings,
    create_series_embeddings,
    create_world_embeddings,
    generate_chapter_content,
)


@receiver(post_save, sender=Character)
def on_character_saved(sender, instance, created, update_fields, **kwargs):
    if created or {"description", "name"}.intersection(update_fields or []):
        character_id: int = instance.id
        on_commit(lambda: create_character_embeddings.delay(character_id))


@receiver(post_save, sender=World)
def on_world_saved(sender, instance, created, update_fields, **kwargs):
    if created or {"description"}.intersection(update_fields or []):
        world_id: int = instance.id
        on_commit(lambda: create_world_embeddings.delay(world_id))


@receiver(post_save, sender=Series)
def on_series_saved(sender, instance, created, update_fields, **kwargs):
    if created:
        series_id: int = instance.id
        on_commit(lambda: create_series_embeddings.delay(series_id))


@receiver(post_save, sender=Chapter)
def on_chapter_saved(sender, instance, created, update_fields, **kwargs):
    if created:
        chapter_id: int = instance.id
        on_commit(lambda: generate_chapter_content(chapter_id))
