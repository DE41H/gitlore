from uuid import uuid4

from django.db.transaction import atomic
from django.utils.text import slugify
from series.services.tree import get_lineage

from series.models import Chapter, ChapterStatus, Character, Series, World

# IMPLEMENT CHUNK COPYING


@atomic
def replicate(
    series_id: int, author_id: int, spin_off_chapter_id: None | int = None
) -> int:
    source = (
        Series.objects.prefetch_related("characters", "genres")
        .select_related("world")
        .get(pk=series_id)
    )
    world = World.objects.create(description=source.world.description)
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
    Character.objects.bulk_create(
        [
            Character(name=c.name, description=c.description, series=series)
            for c in source.characters.all()  # pyright: ignore[reportAttributeAccessIssue]
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
    series_id = replicate(chapter.series_id, author_id, chapter_id)  # pyright: ignore[reportAttributeAccessIssue]
    for chapter_obj in lineage:
        chapter_obj.pk = None
        chapter_obj.uid = uuid4()
        chapter_obj.slug = f"{slugify(chapter_obj.name)}-{chapter_obj.uid.hex[:12]}"
        chapter_obj.parent = None
        chapter_obj.series_id = series_id
        chapter_obj.canon = True
        chapter_obj.status = ChapterStatus.DONE
    created = Chapter.objects.bulk_create(lineage)
    for i in range(1, len(created)):
        created[i].parent = created[i - 1]
    Chapter.objects.bulk_update(created[1:], ["parent"])
    return series_id
