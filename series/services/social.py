from django.db.models import F
from django.db.transaction import atomic

from series.models import Series


@atomic
def toggle_like(series_id: int, user_id: int) -> None:
    series = (
        Series.objects.select_for_update().prefetch_related("likes").get(pk=series_id)
    )
    if any(u.pk == user_id for u in series.likes.all()):
        series.likes.remove(user_id)
        series.like_count = F("like_count") - 1
    else:
        series.likes.add(user_id)
        series.like_count = F("like_count") + 1
    series.save(update_fields=["like_count"])


def add_view(series_id: int) -> None:
    Series.objects.filter(pk=series_id).update(view_count=F("view_count") + 1)
