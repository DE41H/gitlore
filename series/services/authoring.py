from collections import defaultdict
from uuid import uuid4

from django.db.transaction import atomic
from django.utils.text import slugify

from series.models import (
    Chapter,
    ChapterChunk,
    ChapterStatus,
    Character,
    CharacterChunk,
    Series,
    World,
    WorldChunk,
)
from series.services.tree import get_lineage


@atomic
def create_series(
    author_id: int,
    name: str,
    synopsis: str,
    visibility: str,
    world_description: str,
    genre_ids: list[int],
    characters: list[dict] | None = None,
) -> int:
    world = World.objects.create(description="")
    series = Series.objects.create(
        author_id=author_id,
        name=name,
        synopsis=synopsis,
        visibility=visibility,
        world=world,
    )
    series.genres.set(genre_ids)
    World.objects.filter(pk=world.pk).update(description=world_description)
    if characters:
        Character.objects.bulk_create(
            [
                Character(
                    name=c["name"], description=c["description"], series_id=series.pk
                )
                for c in characters
                if c.get("name", "").strip()
            ]
        )
    return series.pk


@atomic
def update_series(
    series_id: int,
    user_id: int,
    name: str,
    synopsis: str,
    visibility: str,
    genre_ids: list[int],
) -> None:
    series = Series.objects.select_for_update().get(pk=series_id)
    if series.author_id != user_id:  # pyright: ignore[reportAttributeAccessIssue]
        raise PermissionError
    series.name = name
    series.synopsis = synopsis
    series.visibility = visibility
    series.save(update_fields=["name", "synopsis", "visibility", "updated_at"])
    series.genres.set(genre_ids)


@atomic
def add_characters(
    series_id: int, user_id: int, name_list: list[str], description_list: list[str]
) -> list[Character]:
    series = Series.objects.select_for_update().only("author_id").get(pk=series_id)
    if series.author_id != user_id:  # pyright: ignore[reportAttributeAccessIssue]
        raise PermissionError
    characters = [
        Character(name=n, description=d, series_id=series_id)
        for n, d in zip(name_list, description_list)
    ]
    return Character.objects.bulk_create(characters)


@atomic
def update_character(
    character_id: int, user_id: int, name: str, description: str
) -> None:
    character = (
        Character.objects.select_related("series")
        .select_for_update()
        .only("series__author_id")
        .get(pk=character_id)
    )
    if character.series.author_id != user_id:
        raise PermissionError
    character.name = name
    character.description = description
    character.save(update_fields=["name", "description"])


@atomic
def update_world(world_id: int, user_id: int, description: str) -> None:
    world = (
        World.objects.select_related("series")
        .select_for_update()
        .only("series__author_id")
        .get(pk=world_id)
    )
    if world.series.author_id != user_id:  # pyright: ignore[reportAttributeAccessIssue]
        raise PermissionError
    world.description = description
    world.save(update_fields=["description"])


@atomic
def delete_character(character_id: int, user_id: int) -> None:
    character = (
        Character.objects.select_related("series")
        .select_for_update()
        .only("series__author_id")
        .get(pk=character_id)
    )
    if character.series.author_id != user_id:
        raise PermissionError
    character.delete()


@atomic
def replicate(
    series_id: int, author_id: int, spin_off_chapter_id: None | int = None
) -> int:
    source = (
        Series.objects.prefetch_related(
            "characters", "genres", "characters__chunks", "world__chunks"
        )
        .select_related("world")
        .get(pk=series_id)
    )
    world = World.objects.create(description=source.world.description)
    WorldChunk.objects.bulk_create(
        [
            WorldChunk(chunk=wc.chunk, embedding=wc.embedding, world=world)
            for wc in source.world.chunks.all()
        ]
    )
    series = Series.objects.create(
        name=source.name,
        synopsis=source.synopsis,
        visibility=source.visibility,
        author_id=author_id,
        world=world,
        spin_off_id=series_id if spin_off_chapter_id is not None else None,
        spin_off_chapter_id=spin_off_chapter_id
        if spin_off_chapter_id is not None
        else None,
    )
    series.genres.set(source.genres.all())
    source_characters = list(source.characters.all())  # pyright: ignore[reportAttributeAccessIssue]
    created = Character.objects.bulk_create(
        [
            Character(name=c.name, description=c.description, series=series)
            for c in source_characters
        ]
    )
    CharacterChunk.objects.bulk_create(
        [
            CharacterChunk(chunk=cc.chunk, embedding=cc.embedding, character=nc)
            for sc, nc in zip(source_characters, created)
            for cc in sc.chunks.all()
        ]
    )
    return series.pk


@atomic
def start_spin_off(chapter_id: int, author_id: int):
    chapter = Chapter.objects.select_for_update().get(pk=chapter_id)
    if chapter.status != ChapterStatus.DONE:
        raise ValueError("Cannot spin off from a chapter that is not done.")
    lineage = get_lineage(chapter.pk)
    not_done = [c.pk for c in lineage if c.status != ChapterStatus.DONE]
    if not_done:
        raise ValueError(f"Cannot spin off: ancestor chapters are not done: {not_done}")
    original_lineage_ids = [c.pk for c in lineage]
    series_id = replicate(chapter.series_id, author_id, chapter_id)  # pyright: ignore[reportAttributeAccessIssue]
    for chapter_obj in lineage:
        chapter_obj.pk = None
        chapter_obj.uid = uuid4()
        chapter_obj.slug = f"{slugify(chapter_obj.name)}-{chapter_obj.uid.hex[:12]}"
        chapter_obj.parent = None
        chapter_obj.series_id = series_id  # pyright: ignore[reportAttributeAccessIssue]
        chapter_obj.canon = True
        chapter_obj.status = ChapterStatus.DONE
    created = Chapter.objects.bulk_create(lineage)
    for i in range(1, len(created)):
        created[i].parent = created[i - 1]
    Chapter.objects.bulk_update(created[1:], ["parent"])
    chunks_by_chapter: dict[int, list] = defaultdict(list)
    for cc in ChapterChunk.objects.filter(chapter__in=original_lineage_ids):
        chunks_by_chapter[cc.chapter_id].append(cc)  # pyright: ignore[reportAttributeAccessIssue]
    ChapterChunk.objects.bulk_create(
        [
            ChapterChunk(chunk=cc.chunk, embedding=cc.embedding, chapter=new_chapter)
            for orig_id, new_chapter in zip(original_lineage_ids, created)
            for cc in chunks_by_chapter[orig_id]
        ]
    )
    return series_id
