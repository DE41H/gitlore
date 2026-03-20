import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
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
        return f"[Character: {self.pk}]"  # pyright: ignore[reportAttributeAccessIssue]

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

    def __str__(self) -> str:
        return f"[World: {self.pk}]"  # pyright: ignore[reportAttributeAccessIssue]

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

    @classmethod
    @transaction.atomic
    def copy(cls, author, source_pk, chapter_pk=None, is_spin_off=False):
        if is_spin_off == (chapter_pk is None):
            raise ValueError("Invalid function parameters.")
        source = (
            cls.objects.prefetch_related("characters", "genres")
            .select_related("world")
            .get(pk=source_pk)
        )
        try:
            source_world = source.world
        except World.DoesNotExist:
            raise ValueError("Source series has no world and cannot be copied.")
        world = World.objects.create(
            description=source_world.description,
            embedding=source_world.embedding,
        )
        series = cls.objects.create(
            name=source.name,
            synopsis=source.synopsis,
            visibility=source.visibility,
            author=author,
            spin_off_id=source_pk if is_spin_off else None,
            spin_off_chapter_id=chapter_pk if is_spin_off else None,
            world=world,
        )
        series.genres.set(source.genres.all())
        Character.objects.bulk_create(
            [
                Character(
                    name=c.name,
                    description=c.description,
                    embedding=c.embedding,
                    series=series,
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
            series.like_count = models.F("like_count") - 1
        else:
            series.likes.add(user)
            series.like_count = models.F("like_count") + 1
        series.save(update_fields=["like_count"])
        self.refresh_from_db(fields=["like_count"])

    def add_view(self):
        Series.objects.filter(pk=self.pk).update(view_count=models.F("view_count") + 1)
        self.refresh_from_db(fields=["view_count"])

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


class ChapterStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    GENERATING = "generating", "Generating"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class Chapter(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=270, blank=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False)
    prompt = models.TextField(validators=[MaxLengthValidator(10000)])
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    canon = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10, choices=ChapterStatus.choices, default=ChapterStatus.PENDING
    )
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)
    series = models.ForeignKey(
        "series.Series", on_delete=models.CASCADE, related_name="chapters"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="children", null=True, blank=True
    )

    @transaction.atomic
    def start_spin_off(self, user):
        if self.status != ChapterStatus.DONE:
            raise ValueError("Cannot spin off from a chapter that is not done.")
        lineage = self.get_lineage()
        not_done = [c.pk for c in lineage if c.status != ChapterStatus.DONE]
        if not_done:
            raise ValueError(
                f"Cannot spin off: ancestor chapters are not done: {not_done}"
            )
        series = Series.copy(user, self.series_id, self.pk, is_spin_off=True)  # pyright: ignore[reportAttributeAccessIssue]
        for chapter_obj in lineage:
            chapter_obj.pk = None
            chapter_obj.uid = uuid.uuid4()
            chapter_obj.slug = f"{slugify(chapter_obj.name)}-{chapter_obj.uid.hex[:12]}"
            chapter_obj.parent = None
            chapter_obj.series = series
            chapter_obj.canon = True
            chapter_obj.status = ChapterStatus.DONE
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
            chapter.canon = False
        else:
            if chapter.status != ChapterStatus.DONE:
                raise ValueError("Cannot set canon if the chapter is not done.")
            if chapter.parent and not chapter.parent.canon:
                raise ValueError(
                    "Parent chapter must be canon to set this chapter as canon."
                )
            if (
                not chapter.parent
                and Chapter.objects.filter(
                    series_id=chapter.series_id,  # pyright: ignore[reportAttributeAccessIssue]
                    canon=True,
                    parent__isnull=True,
                )
                .exclude(pk=chapter.pk)
                .exists()
            ):
                raise ValueError("A canon root chapter already exists for this series.")
            if (
                chapter.parent
                and Chapter.objects.filter(
                    series_id=chapter.series_id,  # pyright: ignore[reportAttributeAccessIssue]
                    canon=True,
                    parent_id=chapter.parent_id,  # pyright: ignore[reportAttributeAccessIssue]
                )
                .exclude(pk=chapter.pk)
                .exists()
            ):
                raise ValueError("A canon chapter already exists for this parent.")
            chapter.canon = True
        chapter.save(update_fields=["canon"])
        self.refresh_from_db(fields=["canon"])

    @transaction.atomic
    def change_parent(self, new_parent_id):
        chapter = (
            Chapter.objects.select_for_update().select_related("parent").get(pk=self.pk)
        )
        new_parent = (
            Chapter.objects.select_for_update()
            .select_related("series")
            .get(pk=new_parent_id)
        )
        if new_parent.series_id != chapter.series_id:  # pyright: ignore[reportAttributeAccessIssue]
            raise ValueError("New parent must belong to the same series.")
        if chapter.canon:
            raise ValueError("Cannot change the parent of a canon chapter.")
        if chapter in new_parent.get_lineage(fields=["id", "parent_id"]):
            raise ValueError("Cannot set a descendant as the new parent.")
        chapter.parent = new_parent
        chapter.save(update_fields=["parent"])
        self.refresh_from_db(fields=["parent"])

    @transaction.atomic
    def remove(self):
        chapter = Chapter.objects.select_for_update().get(pk=self.pk)
        children = Chapter.objects.filter(parent_id=chapter.pk).select_for_update()  # pyright: ignore[reportAttributeAccessIssue]
        if chapter.canon:
            raise ValueError("Cannot delete a canon chapter. Unset canon first.")
        children.update(parent_id=chapter.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
        chapter.delete()

    def get_lineage(self, fields: None | list[str] = None):
        table = self.__class__._meta.db_table
        if fields is not None:
            col_set = sorted(set(fields) | {"id", "parent_id"})
            col_sql = ", ".join(f'"{c}"' for c in col_set)
            recursive_sql = ", ".join(f'c."{c}"' for c in col_set)
        else:
            col_sql = "*"
            recursive_sql = "c.*"

        sql = f"""
            WITH RECURSIVE lineage AS (
                SELECT {col_sql} FROM "{table}" WHERE id = %s
                UNION ALL
                SELECT {recursive_sql} FROM "{table}" c
                INNER JOIN lineage l ON c.id = l.parent_id
            )
            SELECT * FROM lineage
        """
        chapter_map = {c.pk: c for c in Chapter.objects.raw(sql, [self.pk])}
        lineage = []
        visited = set()
        current = chapter_map.get(self.pk)
        while current and current.pk not in visited:
            lineage.append(current)
            visited.add(current.pk)
            current = chapter_map.get(current.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
        return lineage[::-1]

    def get_descendants(self, fields: None | list[str] = None):
        table = self.__class__._meta.db_table
        if fields is not None:
            col_set = sorted(set(fields) | {"id", "parent_id"})
            col_sql = ", ".join(f'"{c}"' for c in col_set)
            recursive_sql = ", ".join(f'c."{c}"' for c in col_set)
        else:
            col_sql = "*"
            recursive_sql = "c.*"

        sql = f"""
            WITH RECURSIVE descendants AS (
                SELECT {col_sql} FROM "{table}" WHERE id = %s
                UNION ALL
                SELECT {recursive_sql} FROM "{table}" c
                INNER JOIN descendants d ON c.parent_id = d.id
            )
            SELECT * FROM descendants
        """
        return list(Chapter.objects.raw(sql, [self.pk]))

    def clean(self):
        if not self.canon:
            return
        if self.status != ChapterStatus.DONE:
            raise ValidationError(
                {"canon": "Chapter must be done to set this chapter as canon."}
            )
        if self.parent_id:  # pyright: ignore[reportAttributeAccessIssue]
            try:
                parent = Chapter.objects.get(pk=self.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
            except Chapter.DoesNotExist:
                raise ValidationError({"parent": "Parent chapter does not exist."})
            if not parent.canon:
                raise ValidationError(
                    {
                        "canon": "Parent chapter must be canon to set this chapter as canon."
                    }
                )
            if (
                Chapter.objects.filter(
                    series_id=self.series_id,  # pyright: ignore[reportAttributeAccessIssue]
                    canon=True,
                    parent_id=self.parent_id,  # pyright: ignore[reportAttributeAccessIssue]
                )
                .exclude(pk=self.pk)
                .exists()
            ):
                raise ValidationError(
                    {"canon": "A canon chapter already exists for this parent."}
                )
        else:
            qs = Chapter.objects.filter(
                series_id=self.series_id,  # pyright: ignore[reportAttributeAccessIssue]
                canon=True,
                parent__isnull=True,
            ).exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    {"canon": "A canon root chapter already exists for this series."}
                )

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
            HnswIndex(
                fields=["embedding"],
                name="chapter_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
