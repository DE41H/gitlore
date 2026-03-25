from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class SeriesVisibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class Series(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=270, blank=True, editable=False)
    uid = models.UUIDField(default=uuid4, editable=False)
    synopsis = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=7, choices=SeriesVisibility.choices, default=SeriesVisibility.PUBLIC
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    view_count = models.PositiveIntegerField(default=0)
    like_count = models.PositiveIntegerField(default=0)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="liked_series", blank=True
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="series"
    )
    spin_off = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="spin_offs",
        null=True,
        blank=True,
    )
    spin_off_chapter = models.ForeignKey(
        "series.Chapter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spin_offs_started",
    )
    world = models.OneToOneField(
        "series.World", on_delete=models.CASCADE, related_name="series"
    )
    genres = models.ManyToManyField("series.Genre", related_name="series")

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{self.uid.hex[:12]}"
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[Series: {self.pk}]"

    class Meta:
        app_label = "series"
        constraints = [
            models.UniqueConstraint(
                fields=["slug", "author"], name="unique_series_slug_per_author"
            ),
            models.CheckConstraint(
                condition=models.Q(like_count__gte=0),
                name="like_count_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(view_count__gte=0),
                name="view_count_non_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["visibility", "-created_at"],
                name="series_visibility_created_idx",
            ),
            models.Index(
                fields=["author", "-created_at"], name="series_author_created_idx"
            ),
        ]
