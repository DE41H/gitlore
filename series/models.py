from django.db import models

# Create your models here.

class Series(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    release_date = models.DateField()
    genre = models.CharField(max_length=100)
    rating = models.FloatField()
