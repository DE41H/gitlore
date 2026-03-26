from django.db.transaction import atomic

from series.models import Chapter


@atomic
def change_parent(chapter_id: int, new_parent_id: int) -> None:
    chapter = Chapter.objects.select_for_update().get(pk=chapter_id)
    old_parent_id = chapter.parent_id  # pyright: ignore[reportAttributeAccessIssue]
    new_parent = Chapter.objects.select_for_update().get(pk=new_parent_id)
    if new_parent.series_id != chapter.series_id:  # pyright: ignore[reportAttributeAccessIssue]
        raise ValueError("New parent must belong to the same series.")
    if chapter.canon:
        raise ValueError("Cannot change the parent of a canon chapter.")
    if new_parent_id == old_parent_id:
        raise ValueError("Parent has not changed.")
    if new_parent_id in {c.pk for c in get_descendants(chapter_id, fields=["id"])}:
        raise ValueError("Cannot set a descendant as the new parent.")
    chapter.parent = new_parent
    chapter.save(update_fields=["parent_id"])


def get_lineage(chapter_id: int, fields: None | list[str] = None) -> list[Chapter]:
    chapter = Chapter.objects.get(pk=chapter_id)
    table = chapter.__class__._meta.db_table
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
    chapter_map = {c.pk: c for c in Chapter.objects.raw(sql, [chapter_id])}
    lineage = []
    visited = set()
    current = chapter_map.get(chapter_id)
    while current and current.pk not in visited:
        lineage.append(current)
        visited.add(current.pk)
        current = chapter_map.get(current.parent_id)  # pyright: ignore[reportAttributeAccessIssue]
    return lineage


def get_descendants(chapter_id: int, fields: None | list[str] = None) -> list[Chapter]:
    chapter = Chapter.objects.get(pk=chapter_id)
    table = chapter.__class__._meta.db_table
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
    return list(Chapter.objects.raw(sql, [chapter_id]))
