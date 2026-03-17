from django.conf import settings
from django.db import models, transaction
from pgvector.django import HnswIndex, VectorField

# NOTES:
# - FIX STEMMING
# - ADD SPIN-OFF MAKING
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
    series = models.ForeignKey('series.Series', on_delete=models.CASCADE, related_name='characters')
    description = models.TextField()
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
        return f"[World: , Series: {self.series.name}]"

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
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='series')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked', blank=True)
    like_count = models.PositiveIntegerField(default=0)
    visibility = models.CharField(max_length=20, choices=SeriesVisibility.choices, default=SeriesVisibility.PUBLIC)
    spin_off = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='spin_offs', null=True, blank=True)

    @transaction.atomic
    def like(self, user):
        series = Series.objects.select_for_update().get(pk=self.pk)
        if not series.likes.filter(id=user.id).exists():
            series.likes.add(user)
            series.like_count = models.F('like_count') + 1
            series.save(update_fields=['like_count'])

    @transaction.atomic
    def unlike(self, user):
        series = Series.objects.select_for_update().get(pk=self.pk)
        if series.likes.filter(id=user.id).exists():
            series.likes.remove(user)
            series.like_count = models.F('like_count') - 1
            series.save(update_fields=['like_count'])

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
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chapters')
    root = models.ForeignKey('series.Series', on_delete=models.CASCADE, related_name='nodes')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='children', null=True, blank=True)
    prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stem = models.BooleanField(default=False)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null = True)

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
