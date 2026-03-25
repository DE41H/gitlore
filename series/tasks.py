from celery import shared_task

from series.ai.embedding import embed_series
from series.ai.generation import generate_chapter_content
from series.models import ChapterStatus


@shared_task(bind=True)
def create_embeddings(self, series_id: int) -> None:
    embed_series(series_id)


@shared_task(bind=True)
def generate_chapter(self, chapter_id: int) -> None:
    generate_chapter_content(chapter_id)
