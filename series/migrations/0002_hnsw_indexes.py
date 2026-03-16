from django.db import migrations
from pgvector.django import HnswIndex


class Migration(migrations.Migration):

    dependencies = [
        ('series', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql='CREATE EXTENSION IF NOT EXISTS vector',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddIndex(
            model_name='chapter',
            index=HnswIndex(
                fields=['embedding'],
                name='chapter_embedding_hnsw',
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),
        migrations.AddIndex(
            model_name='character',
            index=HnswIndex(
                fields=['embedding'],
                name='character_embedding_hnsw',
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),
        migrations.AddIndex(
            model_name='world',
            index=HnswIndex(
                fields=['embedding'],
                name='world_embedding_hnsw',
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),
    ]
