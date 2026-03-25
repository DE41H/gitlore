from celery import shared_task

from series.ai.embedding import embed_character, embed_series, embed_world


@shared_task(bind=True)
def create_series_embeddings(self, series_id: int) -> None:
    embed_series(series_id)


@shared_task(bind=True)
def create_world_embeddings(self, world_id: int) -> None:
    embed_world(world_id)


@shared_task(bind=True)
def create_character_embeddings(self, character_id: int) -> None:
    embed_character(character_id)
