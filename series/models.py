from django.conf import settings
from django.db import models, transaction
from django.db.utils import IntegrityError
from pgvector.django import HnswIndex, VectorField

# NOTES:
# - FIX STEMMING
# - THINK OF THE LOGIC BETTER
# - IMPLEMENT CHUNKING


# Create your models here.

EMBEDDING_DIMENSIONS = 1536


class Genre(models.Model):
    name = models.CharField(max_length=255, unique=True)
    series = models.ManyToManyField('series.Series', related_name='genres')

    def __str__(self) -> str:
        return f"[Genre: {self.name}]"


class Character(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    series = models.ForeignKey('series.Series', on_delete=models.CASCADE, related_name='characters')
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null = True)

    def __str__(self) -> str:
        return f"[Character: {self.name}, Series: {self.series.name}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'series'],
                name='unique_character_name_per_series'
            )
        ]
        indexes = [
            HnswIndex(
                fields=['embedding'],
                name='character_embedding_hnsw_idx',
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops']
            )
        ]


class World(models.Model):
    description = models.TextField()
    series = models.OneToOneField('series.Series', on_delete=models.CASCADE, related_name='world')
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null = True)

    def __str__(self) -> str:
        return f"[World: {self.pk}, Series: {self.series.name}]"

    class Meta:
        indexes = [
            HnswIndex(
                fields=['embedding'],
                name='world_embedding_hnsw_idx',
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops']
            )
        ]


class SeriesVisibility(models.TextChoices):
    PUBLIC = 'public', 'Public'
    PRIVATE = 'private', 'Private'


class Series(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    visibility = models.CharField(max_length=7, choices=SeriesVisibility.choices, default=SeriesVisibility.PUBLIC)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='series')
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked', blank=True)
    like_count = models.PositiveIntegerField(default=0)
    spin_off = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='spin_offs', null=True, blank=True)

    @transaction.atomic
    def like(self, user):
        series = Series.objects.select_for_update().get(pk=self.pk)
        if not series.likes.filter(id=user.id).exists():
            series.likes.add(user)
            series.like_count = models.F('like_count') + 1
            series.save(update_fields=['like_count'])
            self.refresh_from_db(fields=['like_count'])

    @transaction.atomic
    def unlike(self, user):
        series = Series.objects.select_for_update().get(pk=self.pk)
        if series.likes.filter(id=user.id).exists():
            series.likes.remove(user)
            series.like_count = models.F('like_count') - 1
            series.save(update_fields=['like_count'])
            self.refresh_from_db(fields=['like_count'])

    @transaction.atomic
    def create_copy(self, author, spin_off = None):
        name = self.name
        i = 0
        while True:
            savepoint = transaction.savepoint()
            try:
                series = Series.objects.create(
                    name = name,
                    description = self.description,
                    author = author,
                    spin_off = self if spin_off else None,
                )
                transaction.savepoint_commit(savepoint)
                break
            except IntegrityError:
                transaction.savepoint_rollback(savepoint)
                i += 1
                name = f"{self.name}-{i}"
        series.genres.set(self.genres.all())  # pyright: ignore[reportAttributeAccessIssue]

        World.objects.create(
            description = self.world.description,  # pyright: ignore[reportAttributeAccessIssue]
            series = series,
            embedding = self.world.embedding   # pyright: ignore[reportAttributeAccessIssue]
        )

        characters: list[Character] = [
            Character(
                name = character.name,
                description = character.description,
                series = series,
                embedding = character.embedding
            )
            for character in self.characters.all()  # pyright: ignore[reportAttributeAccessIssue]
        ]
        Character.objects.bulk_create(characters)

        return series

    def __str__(self) -> str:
        return f"[Series: {self.name}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'author'],
                name='unique_series_name_per_author'
            ),
            models.CheckConstraint(
                condition=models.Q(like_count__gte=0),
                name='like_count_must_be_non_negative'
            )
        ]


class Chapter(models.Model):
    name = models.CharField(max_length=255)
    prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stem = models.BooleanField(default=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chapters')
    root = models.ForeignKey('series.Series', on_delete=models.CASCADE, related_name='nodes')
    parent = models.ForeignKey('self', on_delete=models.PROTECT, related_name='children', null=True, blank=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null = True)

    @transaction.atomic
    def create_spin_off(self, user):
        root = Series.objects.prefetch_related('characters', 'genres').select_related('world').get(pk=self.root_id)  # pyright: ignore[reportAttributeAccessIssue]
        series = root.create_copy(user, spin_off=True)
        chapter_map = { c.pk: c for c in Chapter.objects.filter(root=root).only('name', 'author', 'parent', 'prompt', 'embedding') }
        lineage = []
        current = chapter_map[self.pk]
        while current is not None:
            lineage.append(
                Chapter(
                    name = current.name,
                    prompt = current.prompt,
                    stem = True,
                    author_id = current.author_id,  # pyright: ignore[reportAttributeAccessIssue]
                    root = series,
                    embedding = current.embedding
                )
            )
            current = chapter_map.get(current.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
        lineage.reverse()
        created = Chapter.objects.bulk_create(lineage)

        for i in range(1, len(created)):
            created[i].parent = created[i - 1]
        if len(created) > 1:
            Chapter.objects.bulk_update(created[1:], ['parent'])

        return series

    def __str__(self) -> str:
        return f"[Chapter: {self.name}, Series: {self.root.name}]"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'root'],
                name='unique_chapter_name_per_series'
            )
        ]
        indexes = [
            HnswIndex(
                fields=['embedding'],
                name='chapter_embedding_hnsw_idx',
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops']
            )
        ]
