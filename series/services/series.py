from django.db.transaction import atomic

from series.models import Genre, Series, SeriesVisibility


def get_public_series(author_id: int | None = None):
    qs = (
        Series.objects.select_related("author")
        .prefetch_related("genres")
        .filter(visibility=SeriesVisibility.PUBLIC, author_id=author_id)
        .order_by("-created_at")
    )
    return qs


def get_user_series(user_id: int):
    qs = (
        Series.objects.select_related("author")
        .prefetch_related("genres")
        .filter(author_id=user_id)
        .order_by("-created_at")
    )
    return qs


def get_series_detail(series_id: int) -> Series:
    qs = (
        Series.objects.select_related("world", "author")
        .prefetch_related("genres", "characters")
        .get(pk=series_id)
    )
    return qs


def get_genre_list():
    qs = Genre.objects.all().order_by("name")
    return qs


def get_spin_off_series(chapter_id: int):
    qs = (
        Series.objects.select_related("author")
        .filter(spin_off_chapter_id=chapter_id)
        .order_by("-created_at")
    )
    return qs


@atomic
def delete_series(series_id: int, user_id: int) -> None:
    series = Series.objects.select_for_update().get(pk=series_id)
    if series.author_id != user_id:  # pyright: ignore[reportAttributeAccessIssue]
        raise PermissionError
    series.delete()
