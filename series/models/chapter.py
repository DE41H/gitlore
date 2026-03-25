from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.db.transaction import atomic
from django.utils.text import slugify
from pgvector.django import HnswIndex, VectorField


class ChapterStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    GENERATING = "generating", "Generating"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class Chapter(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=270, blank=True)
    uid = models.UUIDField(default=uuid4, editable=False)
    prompt = models.TextField(validators=[MaxLengthValidator(10000)])
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    canon = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10, choices=ChapterStatus.choices, default=ChapterStatus.PENDING
    )
    series = models.ForeignKey(
        "series.Series", on_delete=models.CASCADE, related_name="chapters"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="children", null=True, blank=True
    )

    @atomic
    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        chapter = Chapter.objects.select_for_update().get(pk=self.pk)
        if self.canon:
            raise ValidationError("Cannot delete a canon chapter")
        Chapter.objects.filter(parent_id=self.pk).update(parent_id=chapter.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{self.uid.hex[:12]}"
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[Chapter: {self.pk}]"

    class Meta:
        app_label = "series"
        constraints = [
            models.UniqueConstraint(
                fields=["slug", "series"], name="unique_chapter_slug_per_series"
            ),
            models.UniqueConstraint(
                fields=["parent", "series"],
                condition=models.Q(canon=True),
                name="unique_canon_child_per_parent",
            ),
            models.UniqueConstraint(
                fields=["series"],
                condition=models.Q(canon=True, parent__isnull=True),
                name="unique_canon_root_per_series",
            ),
            models.CheckConstraint(
                condition=models.Q(canon=False)
                | models.Q(canon=True, status=ChapterStatus.DONE),
                name="canon_chapter_must_be_done",
            ),
        ]
        indexes = [
            models.Index(fields=["series", "canon"], name="chapter_series_canon_idx"),
            models.Index(
                fields=["series", "-created_at"], name="chapter_series_created_idx"
            ),
        ]


class ChapterChunk(models.Model):
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS)
    chapter = models.ForeignKey(
        "series.Chapter", on_delete=models.CASCADE, related_name="chunks"
    )

    def __str__(self) -> str:
        return f"[ChapterChunk: {self.pk}]"

    class Meta:
        app_label = "series."
        indexes = [
            HnswIndex(
                fields=["embedding"],
                name="chapter_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
