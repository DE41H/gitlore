from django.db.transaction import atomic
from google.genai import types

from series.ai.gemini import client, embedding_model
from series.models import (
    Character,
    CharacterChunk,
    Series,
    World,
    WorldChunk,
)
from series.services.text import split_text

EMBED_BATCH_SIZE = 200


def get_embeddings(text_list: list[str], task_type: str = "retrieval_document") -> list:
    embeddings = []
    for i in range(0, len(text_list), EMBED_BATCH_SIZE):
        batch = text_list[i : i + EMBED_BATCH_SIZE]
        response = client.models.embed_content(
            model=embedding_model,
            contents=batch,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        if not response.embeddings:
            raise ValueError(
                f"Embedding API returned no embeddings for batch starting at index {i}"
            )
        embeddings.extend([e.values for e in response.embeddings])
    return embeddings


def embed_world(world_id: int) -> None:
    world = World.objects.get(pk=world_id)
    chunks = split_text(world.description)
    embeddings = get_embeddings(chunks)
    with atomic():
        WorldChunk.objects.filter(world=world_id).delete()
        WorldChunk.objects.bulk_create(
            [
                WorldChunk(world=world, embedding=e, chunk=c)
                for e, c in zip(embeddings, chunks)
            ]
        )


def embed_character(character_id: int) -> None:
    character = Character.objects.get(pk=character_id)
    chunks = split_text(character.description)
    embeddings = get_embeddings([f"{character.name}: {chunk}" for chunk in chunks])
    with atomic():
        CharacterChunk.objects.filter(character=character).delete()
        CharacterChunk.objects.bulk_create(
            [
                CharacterChunk(character=character, embedding=e, chunk=c)
                for e, c in zip(embeddings, chunks)
            ]
        )


def embed_series(series_id: int) -> None:
    series = Series.objects.get(pk=series_id)
    world = World.objects.get(pk=series.world_id)  # pyright: ignore[reportAttributeAccessIssue]
    characters = list(
        Character.objects.filter(series=series.pk).only("id", "name", "description")
    )
    world_chunks = split_text(world.description)
    character_chunks = {c: split_text(c.description) for c in characters}
    combined_texts = world_chunks + [
        f"{c.name}: {chunk}"
        for c, chunks in character_chunks.items()
        for chunk in chunks
    ]
    all_embeddings = get_embeddings(combined_texts)
    world_embeddings = all_embeddings[: len(world_chunks)]
    offset = len(world_chunks)
    all_character_chunks = []
    for c, chunks in character_chunks.items():
        char_embeddings = all_embeddings[offset : offset + len(chunks)]
        offset += len(chunks)
        all_character_chunks.extend(
            CharacterChunk(character=c, embedding=e, chunk=t)
            for e, t in zip(char_embeddings, chunks)
        )
    with atomic():
        WorldChunk.objects.filter(world=world).delete()
        WorldChunk.objects.bulk_create(
            [
                WorldChunk(world=world, embedding=e, chunk=t)
                for e, t in zip(world_embeddings, world_chunks)
            ]
        )
        CharacterChunk.objects.filter(character__series=series.pk).delete()
        CharacterChunk.objects.bulk_create(all_character_chunks)
