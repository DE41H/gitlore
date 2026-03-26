from django.db.transaction import atomic

from series.models import Chapter, ChapterStatus


@atomic
def toggle_canon(chapter_id: int) -> None:
    chapter = (
        Chapter.objects.select_for_update()
        .select_related("parent")
        .prefetch_related("children")
        .get(pk=chapter_id)
    )
    parent_id = chapter.parent_id  # pyright: ignore[reportAttributeAccessIssue]
    if chapter.children.filter(canon=True).exists():  # pyright: ignore[reportAttributeAccessIssue]
        raise ValueError("Cannot unset if there are canon children.")
    if chapter.canon:
        chapter.canon = False
    elif chapter.status != ChapterStatus.DONE:
        raise ValueError("Cannot set canon if the chapter is not done.")
    elif parent_id and not chapter.parent.canon:
        raise ValueError("Parent chapter must be canon to set this chapter as canon.")
    elif (
        parent_id is None
        and Chapter.objects.filter(
            series_id=chapter.series_id,  # pyright: ignore[reportAttributeAccessIssue]
            canon=True,
            parent__isnull=True,
        ).exists()
    ):
        raise ValueError("A canon root chapter already exists for this series.")
    elif (
        parent_id
        and Chapter.objects.filter(
            series_id=chapter.series_id,  # pyright: ignore[reportAttributeAccessIssue]
            canon=True,
            parent_id=parent_id,
        ).exists()
    ):
        raise ValueError("A canon chapter already exists for this parent.")
    else:
        chapter.canon = True
    chapter.save(update_fields=["canon"])
