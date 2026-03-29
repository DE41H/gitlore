from django import template

register = template.Library()


@register.filter
def get_children(tree, parent_pk):
    """Return child chapters from the tree dict for a given parent pk."""
    return tree.get(parent_pk, [])


@register.filter
def modulo(value, arg):
    """Return value % arg — used for cycling through gradient classes."""
    try:
        return int(value) % int(arg)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
