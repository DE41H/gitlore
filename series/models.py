from django.conf import settings
from django.db import models
from django.db import transaction
from pgvector.django import VectorField

# Create your models here.

EMBEDDING_DIMENSIONS = 1536


class Genre(models.Model):
    name = models.CharField(max_length=255, unique=True)
    series = models.ManyToManyField('series.Series', related_name='genres')


class Character(models.Model):
    name = models.CharField(max_length=255)
    series = models.ForeignKey('series.Series', on_delete=models.CASCADE, related_name='characters')
    description = models.TextField()
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)

    class Meta:
        unique_together = ('name', 'series')


class World(models.Model):
    description = models.TextField()
    series = models.OneToOneField('series.Series', on_delete=models.CASCADE, related_name='world')
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)


class SeriesVisibility(models.TextChoices):
    PUBLIC = 'public', 'Public'
    PRIVATE = 'private', 'Private'


class Series(models.Model):
    name = models.CharField(max_length=255)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='series')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked', blank=True)
    like_count = models.IntegerField(default=0)
    visibility = models.CharField(max_length=20, choices=SeriesVisibility.choices, default=SeriesVisibility.PUBLIC)

    @transaction.atomic()
    def like(self, user):
        if not self.likes.filter(id=user.id).exists():
            self.likes.add(user)
            self.objects.filter(pk=self.pk).update(like_count = models.F('like_count') + 1)

    @transaction.atomic()
    def unlike(self, user):
        if self.likes.filter(id=user.id).exists():
            self.likes.remove(user)
            Series.objects.filter(pk=self.pk).update(like_count = models.F('like_count') - 1)

    class Meta:
        unique_together = ('name', 'author')


class Chapter(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chapters')
    root = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='nodes')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='children', null=True, blank=True)
    prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)
