from django.db.transaction import atomic
from google.genai import types

from series.ai.gemini import client, embedding_model
from series.models import Character, CharacterChunk, Series, World, WorldChunk
from series.services.text import split_text

EMBED_BATCH_SIZE = 100  # CALCULATE BATCH SIZE AND ADD SAFETY MEASURES SO USERS DONT PROVIDE TOO MUCH CONTEXT


def get_embeddings(text_list: list[str], task_type: str = "retrieval_document") -> list:
    embeddings = []
    for i in range(0, len(text_list), EMBED_BATCH_SIZE):
        batch = text_list[i : i + EMBED_BATCH_SIZE]
        response = client.models.embed_content(
            model=embedding_model,
            contents=batch,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        if response.embeddings:
            embeddings.extend([e.values for e in response.embeddings])
    return embeddings


def embed_world(world_id: int, embeddings: list | None = None) -> None:
    world = World.objects.get(pk=world_id)
    if embeddings is None:
        chunks = split_text(world.description)
        embeddings = get_embeddings(chunks)
    with atomic():
        WorldChunk.objects.filter(world_id=world_id).delete()
        WorldChunk.objects.bulk_create(
            [WorldChunk(world=world, embedding=e) for e in embeddings]
        )


def embed_character(character_id: int, embeddings: list | None = None) -> None:
    character = Character.objects.get(pk=character_id)
    if embeddings is None:
        chunks = split_text(character.description)
        embeddings = get_embeddings([f"{character.name}: {chunk}" for chunk in chunks])
    with atomic():
        CharacterChunk.objects.filter(character=character).delete()
        CharacterChunk.objects.bulk_create(
            [CharacterChunk(character=character, embedding=e) for e in embeddings]
        )


def embed_series(series_id: int) -> None:
    series = Series.objects.get(pk=series_id)
    world = World.objects.get(pk=series.world_id)  # pyright: ignore[reportAttributeAccessIssue]
    characters = list(
        Character.objects.filter(series_id=series.pk).only("id", "name", "description")
    )
    world_chunks = split_text(world.description)
    character_chunks = {c: split_text(c.description) for c in characters}
    combined_texts = [*world_chunks] + [
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
            CharacterChunk(character=c, embedding=e) for e in char_embeddings
        )
    with atomic():
        WorldChunk.objects.filter(world=world).delete()
        WorldChunk.objects.bulk_create(
            [WorldChunk(world=world, embedding=e) for e in world_embeddings]
        )
        CharacterChunk.objects.filter(character__series_id=series.pk).delete()
        CharacterChunk.objects.bulk_create(all_character_chunks)
