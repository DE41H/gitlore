from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models
from pgvector.django import HnswIndex, VectorField


class Character(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(validators=[MaxLengthValidator(2000)])
    series = models.ForeignKey(
        "series.Series", on_delete=models.CASCADE, related_name="characters"
    )

    def __str__(self) -> str:
        return f"[Character: {self.pk}]"

    class Meta:
        app_label = "series"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "series"], name="unique_character_name_per_series"
            )
        ]


class CharacterChunk(models.Model):
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS)
    character = models.ForeignKey(
        "series.Character", on_delete=models.CASCADE, related_name="chunks"
    )

    def __str__(self) -> str:
        return f"[CharacterChunk: {self.pk}]"

    class Meta:
        app_label = "series"
        indexes = [
            HnswIndex(
                fields=["embedding"],
                name="character_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]
