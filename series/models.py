import copy
import uuid

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.utils.text import slugify
from pgvector.django import HnswIndex, VectorField

# - IMPLEMENT CHUNKING

# Create your models here.

EMBEDDING_DIMENSIONS = 1536


class Genre(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=270, unique=True, blank=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False)
    series = models.ManyToManyField("series.Series", related_name="genres")

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{self.uid.hex[:12]}"
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[Genre: {self.pk}]"


class Character(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(validators=[MaxLengthValidator(2000)])
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)
    series = models.ForeignKey(
        "series.Series", on_delete=models.CASCADE, related_name="characters"
    )

    def __str__(self) -> str:
        return f"[Character: {self.pk}, Series: {self.series_id}]"  # pyright: ignore[reportAttributeAccessIssue]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "series"], name="unique_character_name_per_series"
            )
        ]
        indexes = [
            HnswIndex(
                fields=["embedding"],
                name="character_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]


class World(models.Model):
    description = models.TextField(validators=[MaxLengthValidator(5000)])
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)
    series = models.OneToOneField(
        "series.Series", on_delete=models.CASCADE, related_name="world"
    )

    def __str__(self) -> str:
        return f"[World: {self.pk}, Series: {self.series_id}]"  # pyright: ignore[reportAttributeAccessIssue]

    class Meta:
        indexes = [
            HnswIndex(
                fields=["embedding"],
                name="world_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]


class SeriesVisibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class Series(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=270, blank=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False)
    synopsis = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    visibility = models.CharField(
        max_length=7, choices=SeriesVisibility.choices, default=SeriesVisibility.PUBLIC
    )
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

    @classmethod
    @transaction.atomic
    def create_copy(cls, source_pk, author, is_spin_off=False):
        source = (
            cls.objects.prefetch_related("characters", "genres")
            .select_related("world")
            .get(pk=source_pk)
        )
        series = cls.objects.create(
            name=source.name,
            synopsis=source.synopsis,
            author=author,
            spin_off_id=source_pk if is_spin_off else None,
        )
        series.genres.set(source.genres.all())  # pyright: ignore[reportAttributeAccessIssue]
        World.objects.create(
            description=source.world.description,  # pyright: ignore[reportAttributeAccessIssue]
            series=series,
            embedding=source.world.embedding,  # pyright: ignore[reportAttributeAccessIssue]
        )
        Character.objects.bulk_create(
            [
                Character(
                    name=c.name,
                    description=c.description,
                    series=series,
                    embedding=c.embedding,
                )
                for c in source.characters.all()  # pyright: ignore[reportAttributeAccessIssue]
            ]
        )
        return series

    @transaction.atomic
    def toggle_like(self, user):
        series = Series.objects.select_for_update().get(pk=self.pk)
        if series.likes.filter(pk=user.pk).exists():
            series.likes.remove(user)
            Series.objects.filter(pk=self.pk).update(
                like_count=models.F("like_count") - 1
            )
        else:
            series.likes.add(user)
            Series.objects.filter(pk=self.pk).update(
                like_count=models.F("like_count") + 1
            )
        self.refresh_from_db(fields=["like_count"])

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{self.uid.hex[:12]}"
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[Series: {self.pk}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["slug", "author"], name="unique_series_slug_per_author"
            ),
            models.CheckConstraint(
                condition=models.Q(like_count__gte=0),
                name="like_count_non_negative",
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


class Chapter(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=270, blank=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False)
    prompt = models.TextField(validators=[MaxLengthValidator(10000)])
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    canon = models.BooleanField(default=False)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)
    series = models.ForeignKey(
        "series.Series", on_delete=models.CASCADE, related_name="chapters"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="children", null=True, blank=True
    )

    @transaction.atomic
    def start_spin_off(self, user):
        series = Series.create_copy(self.series_id, user, is_spin_off=True)  # pyright: ignore[reportAttributeAccessIssue]
        lineage = self.get_lineage()
        for chapter_obj in lineage:
            chapter_obj.pk = None
            chapter_obj.slug = f"{slugify(chapter_obj.name)}-{chapter_obj.uid.hex[:12]}"
            chapter_obj.series = series
            chapter_obj.canon = True
        created = Chapter.objects.bulk_create(lineage)
        for i in range(1, len(created)):
            created[i].parent = created[i - 1]
        Chapter.objects.bulk_update(created[1:], ["parent"])
        return series

    @transaction.atomic
    def toggle_canon(self):
        chapter = (
            Chapter.objects.select_for_update().select_related("parent").get(pk=self.pk)
        )
        if chapter.canon:
            if chapter.children.filter(canon=True).exists():  # pyright: ignore[reportAttributeAccessIssue]
                raise ValueError(
                    "Cannot unset canon if there are canon children. Unset canon on children first."
                )
            Chapter.objects.filter(pk=self.pk).update(canon=False)
        else:
            if chapter.parent and not chapter.parent.canon:
                raise ValueError(
                    "Parent chapter must be canon to set this chapter as canon."
                )
            Chapter.objects.filter(pk=self.pk).update(canon=True)
        self.refresh_from_db(fields=["canon"])

    @transaction.atomic
    def change_parent(self, new_parent_id):
        chapter = (
            Chapter.objects.select_for_update().select_related("parent").get(pk=self.pk)
        )
        if not Chapter.objects.filter(
            pk=new_parent_id,
            series_id=chapter.series_id,  # pyright: ignore[reportAttributeAccessIssue]
        ).exists():
            raise ValueError("New parent must belong to the same series.")
        if chapter.canon:
            raise ValueError("Cannot change the parent of a canon chapter.")
        if self in Chapter.objects.get(id=new_parent_id).get_lineage():
            raise ValueError("Cannot set a descendant as the new parent.")
        Chapter.objects.filter(pk=self.pk).update(parent_id=new_parent_id)
        self.refresh_from_db(fields=["parent"])

    @transaction.atomic
    def remove(self):
        chapter = Chapter.objects.select_for_update().get(pk=self.pk)
        if chapter.canon:
            raise ValueError("Cannot delete a canon chapter. Unset canon first.")
        Chapter.objects.filter(parent_id=chapter.pk).update(parent_id=chapter.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
        chapter.delete()

    def get_lineage(self):
        chapter_map = {
            c.pk: copy.copy(c)
            for c in Chapter.objects.filter(series_id=self.series_id)  # pyright: ignore[reportAttributeAccessIssue]
        }
        lineage = []
        current = chapter_map[self.pk]
        while current:
            lineage.append(current)
            current = chapter_map.get(current.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
        return lineage[::-1]

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{self.uid.hex[:12]}"
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[Chapter: {self.pk}, Series: {self.series_id}]"  # pyright: ignore[reportAttributeAccessIssue]

    class Meta:
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
        ]
        indexes = [
            models.Index(fields=["series", "canon"], name="chapter_series_canon_idx"),
            models.Index(
                fields=["series", "-created_at"], name="chapter_series_created_idx"
            ),
            HnswIndex(
                fields=["embedding"],
                name="chapter_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
