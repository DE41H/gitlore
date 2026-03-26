from celery import shared_task
from celery.app.task import Task
from google.genai.errors import APIError

from series.ai.embedding import embed_character, embed_series, embed_world
from series.ai.generation import generate_content


@shared_task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    autoretry_for=(APIError, ConnectionError, TimeoutError),
)
def create_series_embeddings(self: Task, series_id: int) -> None:
    embed_series(series_id)


@shared_task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    autoretry_for=(APIError, ConnectionError, TimeoutError),
)
def create_world_embeddings(self: Task, world_id: int) -> None:
    embed_world(world_id)


@shared_task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    autoretry_for=(APIError, ConnectionError, TimeoutError),
)
def create_character_embeddings(self: Task, character_id: int) -> None:
    embed_character(character_id)


@shared_task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    autoretry_for=(APIError, ConnectionError, TimeoutError),
)
def generate_chapter_content(self: Task, chapter_id: int) -> None:
    generate_content(chapter_id)
