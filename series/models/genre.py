from uuid import uuid4

from django.db import models
from django.utils.text import slugify


class Genre(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=270, unique=True, blank=True, editable=False)
    uid = models.UUIDField(default=uuid4, editable=False)

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = f"{base_slug}-{self.uid.hex[:12]}"
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[Genre: {self.pk}]"

    class Meta:
        app_label = "series"
