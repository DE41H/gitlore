from django.core.validators import MaxLengthValidator
from django.db import models
from pgvector.django import HnswIndex, VectorField

from series.ai.embedding import EMBEDDING_DIMENSIONS


class World(models.Model):
    description = models.TextField(validators=[MaxLengthValidator(5000)])

    def __str__(self) -> str:
        return f"[World: {self.pk}]"

    class Meta:
        app_label = "series"


class WorldChunk(models.Model):
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS)
    world = models.ForeignKey(
        "series.World", on_delete=models.CASCADE, related_name="chunks"
    )

    def __str__(self) -> str:
        return f"[WorldChunk: {self.pk}]"

    class Meta:
        app_label = "series"
        indexes = [
            HnswIndex(
                fields=["embedding"],
                name="world_embedding_hnsw_idx",
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]
