from django.db.transaction import atomic

from series.models import Chapter, Series


def create_chapter(
    series_id: int,
    user_id: int,
    parent_id: int | None,
    name: str,
    prompt: str,
) -> int:
    series = Series.objects.only("author_id").get(pk=series_id)
    if series.author_id != user_id:  # pyright: ignore[reportAttributeAccessIssue]
        raise PermissionError
    if parent_id is not None:
        parent = Chapter.objects.only("series_id").get(pk=parent_id)
        if parent.series_id != series_id:  # pyright: ignore[reportAttributeAccessIssue]
            raise ValueError("Parent chapter does not belong to this series.")
    chapter = Chapter.objects.create(
        series=series_id,
        parent=parent_id,
        name=name,
        prompt=prompt,
    )
    return chapter.pk


def get_chapter_detail(chapter_id: int) -> Chapter:
    return Chapter.objects.select_related("series", "parent", "series__author").get(
        pk=chapter_id
    )


def get_chapter_tree(series_id: int) -> dict[int | None, list[Chapter]]:
    chapters = list(
        Chapter.objects.filter(series=series_id)
        .only("id", "name", "slug", "status", "canon", "parent_id", "series_id")
        .order_by("created_at")
    )
    tree: dict[int | None, list[Chapter]] = {}
    for ch in chapters:
        tree.setdefault(ch.parent_id, []).append(ch)  # pyright: ignore[reportAttributeAccessIssue]
    return tree


@atomic
def delete_chapter(chapter_id: int, user_id: int) -> None:
    chapter = (
        Chapter.objects.select_related("series")
        .select_for_update()
        .only("series__author_id")
        .get(pk=chapter_id)
    )
    if chapter.series.author_id != user_id:
        raise PermissionError
    chapter.delete()
