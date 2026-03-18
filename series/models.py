from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.utils import IntegrityError
from pgvector.django import HnswIndex, VectorField

# - IMPLEMENT CHUNKING

# Create your models here.

EMBEDDING_DIMENSIONS = 1536


class Genre(models.Model):
    name = models.CharField(max_length=255, unique=True)
    series = models.ManyToManyField("series.Series", related_name="genres")

    def __str__(self) -> str:
        return f"[Genre: {self.name}]"


class Character(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    series = models.ForeignKey(
        "series.Series", on_delete=models.CASCADE, related_name="characters"
    )
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)

    def __str__(self) -> str:
        return f"[Character: {self.name}, Series: {self.series.name}]"

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
    description = models.TextField()
    series = models.OneToOneField(
        "series.Series", on_delete=models.CASCADE, related_name="world"
    )
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)

    def __str__(self) -> str:
        return f"[World: {self.pk}, Series: {self.series.name}]"

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
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    visibility = models.CharField(
        max_length=7, choices=SeriesVisibility.choices, default=SeriesVisibility.PUBLIC
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="series"
    )
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="liked", blank=True
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
        name = source.name
        i = 0
        while True:
            savepoint = transaction.savepoint()
            try:
                series = cls.objects.create(
                    name=name,
                    description=source.description,
                    author=author,
                    spin_off_id=source_pk if is_spin_off else None,
                )
                transaction.savepoint_commit(savepoint)
                break
            except IntegrityError as e:
                if "unique_series_name_per_author" not in str(e):
                    raise
                transaction.savepoint_rollback(savepoint)
                i += 1
                name = f"{source.name}-{i}"
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

    def __str__(self) -> str:
        return f"[Series: {self.name}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "author"], name="unique_series_name_per_author"
            )
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
    prompt = models.TextField()
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stem = models.BooleanField(default=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chapters"
    )
    root = models.ForeignKey(
        "series.Series", on_delete=models.CASCADE, related_name="nodes"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="children", null=True, blank=True
    )
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)

    @transaction.atomic
    def create_spin_off(self, user):
        series = Series.create_copy(self.root_id, user, is_spin_off=True)  # pyright: ignore[reportAttributeAccessIssue]
        chapters = {c.pk: c for c in Chapter.objects.filter(root=self.root)}
        lineage, current = [], self
        while current:
            lineage.append(
                Chapter(
                    name=current.name,
                    prompt=current.prompt,
                    content=current.content,
                    author=user,
                    root=series,
                    stem=True,
                    embedding=current.embedding,
                )
            )
            current = chapters.get(current.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
        lineage.reverse()
        created = Chapter.objects.bulk_create(lineage)

        for i in range(1, len(created)):
            created[i].parent = created[i - 1]
        if len(created) > 1:
            Chapter.objects.bulk_update(created[1:], ["parent"])

        return series

    def clean(self):
        if self.stem and self.parent_id is not None:  # pyright: ignore[reportAttributeAccessIssue]
            if not Chapter.objects.filter(pk=self.parent_id, stem=True).exists():  # pyright: ignore[reportAttributeAccessIssue]
                raise ValidationError(
                    "A stem chapter's parent must also be a stem chapter"
                )
        super().clean()

    def save(self, *args, **kwargs) -> None:
        update_fields = kwargs.get("update_fields")
        if update_fields is None or {"stem", "parent", "parent_id"}.intersection(
            update_fields
        ):
            self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[Chapter: {self.name}, Series: {self.root.name}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "root"], name="unique_chapter_name_per_series"
            ),
            models.UniqueConstraint(
                fields=["parent"],
                condition=models.Q(stem=True),
                name="unique_stem_child_per_parent",
            ),
            models.UniqueConstraint(
                fields=["root"],
                condition=models.Q(stem=True, parent__isnull=True),
                name="unique_stem_root_per_series",
            ),
        ]
        indexes = [
            models.Index(fields=["root", "stem"], name="chapter_root_stem_idx"),
            models.Index(
                fields=["root", "-created_at"], name="chapter_root_created_idx"
            ),
            models.Index(
                fields=["author", "-created_at"], name="chapter_author_created_idx"
            ),
            models.Index(
                fields=["created_at"],
                condition=models.Q(content__isnull=True),
                name="chapter_pending_generation_idx",
            ),
            HnswIndex(
                fields=["embedding"],
                name="chapter_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
