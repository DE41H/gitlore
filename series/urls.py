from django.urls import path

from series import views

app_name = "series"

urlpatterns = [
    path("", views.discover_view, name="discover"),
    path("my/", views.my_series_view, name="my-series"),
    path("filter/", views.genre_filter_view, name="genre-filter"),
    path("create/", views.series_create_view, name="series-create"),
    path("<uuid:series_uid>/", views.series_detail_view, name="series-detail"),
    path("<uuid:series_uid>/edit/", views.series_edit_view, name="series-edit"),
    path("<uuid:series_uid>/delete/", views.series_delete_view, name="series-delete"),
    path("<uuid:series_uid>/like/", views.series_like_view, name="series-like"),
    path(
        "<uuid:series_uid>/spin-off/<uuid:chapter_uid>/",
        views.start_spin_off_view,
        name="start-spin-off",
    ),
    path("<uuid:series_uid>/chapters/", views.chapter_tree_view, name="chapter-tree"),
    path(
        "<uuid:series_uid>/chapters/create/",
        views.chapter_create_view,
        name="chapter-create",
    ),
    path(
        "<uuid:series_uid>/chapters/<uuid:chapter_uid>/",
        views.chapter_detail_view,
        name="chapter-detail",
    ),
    path(
        "<uuid:series_uid>/chapters/<uuid:chapter_uid>/delete/",
        views.chapter_delete_view,
        name="chapter-delete",
    ),
    path(
        "<uuid:series_uid>/chapters/<uuid:chapter_uid>/status/",
        views.chapter_status_view,
        name="chapter-status",
    ),
    path(
        "<uuid:series_uid>/chapters/<uuid:chapter_uid>/canon/",
        views.toggle_canon_view,
        name="toggle-canon",
    ),
    path(
        "<uuid:series_uid>/chapters/<uuid:chapter_uid>/reparent/",
        views.reparent_chapter_view,
        name="reparent-chapter",
    ),
    path(
        "<uuid:series_uid>/chapters/<uuid:chapter_uid>/spin-offs/",
        views.chapter_spinoffs_view,
        name="chapter-spinoffs",
    ),
    path(
        "<uuid:series_uid>/characters/add/",
        views.character_add_view,
        name="character-add",
    ),
    path(
        "<uuid:series_uid>/characters/<int:character_id>/edit/",
        views.character_edit_view,
        name="character-edit",
    ),
    path(
        "<uuid:series_uid>/characters/<int:character_id>/delete/",
        views.character_delete_view,
        name="character-delete",
    ),
    path("<uuid:series_uid>/world/edit/", views.world_edit_view, name="world-edit"),
]
