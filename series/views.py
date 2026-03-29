from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from series.forms import (
    AccountSettingsForm,
    ChapterForm,
    CharacterForm,
    CharacterFormSet,
    ReparentForm,
    SeriesForm,
    SignupForm,
    WorldForm,
)
from series.models import Chapter, Series
from series.services.authoring import (
    add_characters,
    create_series,
    delete_character,
    start_spin_off,
    update_character,
    update_series,
    update_world,
)
from series.services.canon import toggle_canon
from series.services.chapter import create_chapter, delete_chapter, get_chapter_tree
from series.services.series import (
    delete_series,
    get_genre_list,
    get_public_series,
    get_spin_off_series,
    get_user_series,
)
from series.services.social import add_view, get_like_status, toggle_like
from series.services.tree import change_parent, get_lineage

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _get_cached_genres():
    genres = cache.get("genre_list")
    if not genres:
        genres = list(get_genre_list())
        cache.set("genre_list", genres, 3600)
    return genres


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("/")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def account_settings_view(request):
    profile_form = AccountSettingsForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            profile_form = AccountSettingsForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("account-settings")
        elif action == "change_password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password changed.")
                return redirect("account-settings")

    return render(
        request,
        "accounts/settings.html",
        {"profile_form": profile_form, "password_form": password_form},
    )


# ---------------------------------------------------------------------------
# Series views
# ---------------------------------------------------------------------------


def discover_view(request):
    genre_slug = request.GET.get("genre", "").strip()
    qs = get_public_series()
    if genre_slug:
        qs = qs.filter(genres__slug=genre_slug)
    series_list = list(qs)

    if _is_htmx(request):
        return render(
            request, "series/partials/series_list.html", {"series_list": series_list}
        )

    return render(
        request,
        "series/discover.html",
        {
            "series_list": series_list,
            "genres": _get_cached_genres(),
            "active_genre": genre_slug,
        },
    )


def genre_filter_view(request):
    genre_slug = request.GET.get("genre", "").strip()
    qs = get_public_series()
    if genre_slug:
        qs = qs.filter(genres__slug=genre_slug)
    return render(
        request, "series/partials/series_list.html", {"series_list": list(qs)}
    )


@login_required
def my_series_view(request):
    return render(
        request,
        "series/my_series.html",
        {"series_list": list(get_user_series(request.user.pk))},
    )


@login_required
def series_create_view(request):
    if request.method == "POST":
        form = SeriesForm(request.POST, include_world=True)
        formset = CharacterFormSet(request.POST, prefix="characters")
        if form.is_valid() and formset.is_valid():
            d = form.cleaned_data
            characters = [
                {
                    "name": f.cleaned_data["name"],
                    "description": f.cleaned_data.get("description", ""),
                }
                for f in formset
                if f.cleaned_data.get("name", "").strip()
            ]  # pyright: ignore[reportAttributeAccessIssue]
            series_id = create_series(
                author_id=request.user.pk,
                name=d["name"],
                synopsis=d.get("synopsis", ""),
                visibility=d["visibility"],
                world_description=d.get("world_description", ""),
                genre_ids=[g.pk for g in d.get("genres", [])],
                characters=characters or None,
            )
            series = Series.objects.only("uid").get(pk=series_id)
            messages.success(request, "Series created!")
            return redirect("series:series-detail", series_uid=series.uid)
    else:
        form = SeriesForm(include_world=True)
        formset = CharacterFormSet(prefix="characters")
    return render(
        request,
        "series/series_form.html",
        {"form": form, "formset": formset, "editing": False},
    )


def series_detail_view(request, series_uid):
    # Single query — eliminates the previous double-fetch (_resolve_series + get_series_detail)
    series = get_object_or_404(
        Series.objects.select_related("world", "author", "spin_off").prefetch_related(
            "genres", "characters"
        ),
        uid=series_uid,
    )
    if series.visibility == "private" and (
        not request.user.is_authenticated or series.author_id != request.user.pk
    ):
        raise Http404

    add_view(series.pk)
    tree = get_chapter_tree(series.pk)
    is_liked = (
        get_like_status(series.pk, request.user.pk)
        if request.user.is_authenticated
        else False
    )
    is_author = request.user.is_authenticated and series.author_id == request.user.pk

    return render(
        request,
        "series/series_detail.html",
        {"series": series, "tree": tree, "is_liked": is_liked, "is_author": is_author},
    )


@login_required
def series_edit_view(request, series_uid):
    # Only fetch fields the edit form needs — no world/character prefetch
    series = get_object_or_404(
        Series.objects.prefetch_related("genres"),
        uid=series_uid,
    )
    if series.author_id != request.user.pk:
        raise Http404

    if request.method == "POST":
        form = SeriesForm(request.POST, include_world=False)
        if form.is_valid():
            d = form.cleaned_data
            update_series(
                series_id=series.pk,
                user_id=request.user.pk,
                name=d["name"],
                synopsis=d.get("synopsis", ""),
                visibility=d["visibility"],
                genre_ids=[g.pk for g in d.get("genres", [])],
            )
            messages.success(request, "Series updated.")
            return redirect("series:series-detail", series_uid=series.uid)
    else:
        form = SeriesForm(
            initial={
                "name": series.name,
                "synopsis": series.synopsis,
                "visibility": series.visibility,
                "genres": series.genres.all(),
            },
            include_world=False,
        )

    return render(
        request,
        "series/series_form.html",
        {"form": form, "series": series, "editing": True},
    )


@login_required
def series_delete_view(request, series_uid):
    if request.method != "POST":
        return redirect("series:series-detail", series_uid=series_uid)
    series = get_object_or_404(
        Series.objects.only("pk", "author_id", "uid"), uid=series_uid
    )
    try:
        delete_series(series.pk, request.user.pk)
        messages.success(request, "Series deleted.")
    except PermissionError:
        messages.error(request, "You don't have permission to delete this series.")
    return redirect("series:my-series")


@login_required
def series_like_view(request, series_uid):
    if request.method != "POST":
        return HttpResponse(status=405)
    # Resolve with only the fields we need — no extra joins
    series = get_object_or_404(
        Series.objects.only("pk", "uid", "like_count"), uid=series_uid
    )
    toggle_like(series.pk, request.user.pk)
    # Refresh only like_count after toggle
    series.refresh_from_db(fields=["like_count"])
    is_liked = get_like_status(series.pk, request.user.pk)
    return render(
        request,
        "series/partials/like_button.html",
        {"series": series, "is_liked": is_liked},
    )


@login_required
def start_spin_off_view(request, series_uid, chapter_uid):
    if request.method != "POST":
        return redirect(
            "series:chapter-detail", series_uid=series_uid, chapter_uid=chapter_uid
        )
    chapter = get_object_or_404(
        Chapter.objects.only("pk", "uid"), uid=chapter_uid, series__uid=series_uid
    )
    try:
        new_series_id = start_spin_off(chapter.pk, request.user.pk)
        new_series = Series.objects.only("uid").get(pk=new_series_id)
        messages.success(request, "Spin-off series created!")
        return redirect("series:series-detail", series_uid=new_series.uid)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect(
            "series:chapter-detail", series_uid=series_uid, chapter_uid=chapter_uid
        )


# ---------------------------------------------------------------------------
# Chapter views
# ---------------------------------------------------------------------------


def chapter_tree_view(request, series_uid):
    series = get_object_or_404(
        Series.objects.only("pk", "uid", "author_id", "visibility", "name"),
        uid=series_uid,
    )
    if series.visibility == "private" and (
        not request.user.is_authenticated or series.author_id != request.user.pk
    ):
        raise Http404

    tree = get_chapter_tree(series.pk)
    is_author = request.user.is_authenticated and series.author_id == request.user.pk
    return render(
        request,
        "series/chapter_tree.html",
        {"series": series, "tree": tree, "is_author": is_author},
    )


@login_required
def chapter_create_view(request, series_uid):
    series = get_object_or_404(
        Series.objects.only("pk", "uid", "author_id", "name"), uid=series_uid
    )
    if series.author_id != request.user.pk:
        raise Http404

    parent = None
    parent_uid = request.GET.get("parent") or request.POST.get("parent_uid")
    if parent_uid:
        parent = get_object_or_404(
            Chapter.objects.only("pk", "uid", "name", "series_id"), uid=parent_uid
        )
        if parent.series_id != series.pk:
            parent = None

    if request.method == "POST":
        form = ChapterForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            chapter_id = create_chapter(
                series_id=series.pk,
                user_id=request.user.pk,
                parent_id=parent.pk if parent else None,
                name=d["name"],
                prompt=d["prompt"],
            )
            chapter = Chapter.objects.only("uid").get(pk=chapter_id)
            messages.success(request, "Chapter created — generation started!")
            return redirect(
                "series:chapter-detail", series_uid=series.uid, chapter_uid=chapter.uid
            )
    else:
        form = ChapterForm()

    return render(
        request,
        "series/chapter_form.html",
        {"form": form, "series": series, "parent": parent},
    )


def chapter_detail_view(request, series_uid, chapter_uid):
    # Single query with all needed relations — eliminates previous double-fetch
    chapter = get_object_or_404(
        Chapter.objects.select_related("series", "series__author"),
        uid=chapter_uid,
        series__uid=series_uid,
    )
    series = chapter.series
    if series.visibility == "private" and (
        not request.user.is_authenticated or series.author_id != request.user.pk
    ):
        raise Http404

    lineage = get_lineage(
        chapter.pk, fields=["id", "name", "uid", "slug", "canon", "status"]
    )
    lineage = [c for c in lineage if c.pk != chapter.pk]  # exclude self
    is_author = request.user.is_authenticated and series.author_id == request.user.pk

    return render(
        request,
        "series/chapter_detail.html",
        {
            "chapter": chapter,
            "series": series,
            "lineage": lineage,
            "is_author": is_author,
        },
    )


def chapter_status_view(request, series_uid, chapter_uid):
    chapter = get_object_or_404(
        Chapter.objects.only("pk", "uid", "status"),
        uid=chapter_uid,
        series__uid=series_uid,
    )
    response = render(
        request, "series/partials/chapter_status.html", {"chapter": chapter}
    )
    if chapter.status in ("done", "failed"):
        response["HX-Trigger"] = "chapterComplete"
    return response


@login_required
def toggle_canon_view(request, series_uid, chapter_uid):
    if request.method != "POST":
        return HttpResponse(status=405)
    chapter = get_object_or_404(
        Chapter.objects.select_related("series").only(
            "pk", "uid", "canon", "status", "series__author_id"
        ),
        uid=chapter_uid,
        series__uid=series_uid,
    )
    if chapter.series.author_id != request.user.pk:
        return HttpResponse(status=403)
    try:
        toggle_canon(chapter.pk)
        chapter.refresh_from_db(fields=["canon"])
    except ValueError as e:
        return HttpResponse(f'<span class="inline-error">{e}</span>', status=400)
    return render(request, "series/partials/canon_badge.html", {"chapter": chapter})


@login_required
def reparent_chapter_view(request, series_uid, chapter_uid):
    if request.method != "POST":
        return redirect("series:chapter-tree", series_uid=series_uid)
    chapter = get_object_or_404(
        Chapter.objects.select_related("series").only("pk", "series__author_id"),
        uid=chapter_uid,
        series__uid=series_uid,
    )
    if chapter.series.author_id != request.user.pk:
        raise Http404

    form = ReparentForm(request.POST)
    if form.is_valid():
        new_parent = get_object_or_404(
            Chapter.objects.only("pk", "series_id"),
            uid=form.cleaned_data["new_parent_uid"],
        )
        try:
            change_parent(chapter.pk, new_parent.pk)
            messages.success(request, "Chapter moved.")
        except ValueError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Invalid parent chapter.")

    return redirect("series:chapter-tree", series_uid=series_uid)


def chapter_spinoffs_view(request, series_uid, chapter_uid):
    chapter = get_object_or_404(
        Chapter.objects.only("pk"), uid=chapter_uid, series__uid=series_uid
    )
    return render(
        request,
        "series/partials/spinoff_list.html",
        {"spinoffs": list(get_spin_off_series(chapter.pk))},
    )


@login_required
def chapter_delete_view(request, series_uid, chapter_uid):
    if request.method != "POST":
        return redirect("series:chapter-tree", series_uid=series_uid)
    chapter = get_object_or_404(
        Chapter.objects.only("pk", "uid"), uid=chapter_uid, series__uid=series_uid
    )
    try:
        delete_chapter(chapter.pk, request.user.pk)
        messages.success(request, "Chapter deleted.")
    except PermissionError:
        messages.error(request, "You don't have permission to delete this chapter.")
    except ValidationError as e:
        messages.error(request, str(e.message))
    return redirect("series:chapter-tree", series_uid=series_uid)


# ---------------------------------------------------------------------------
# Character views
# ---------------------------------------------------------------------------


@login_required
def character_add_view(request, series_uid):
    series = get_object_or_404(
        Series.objects.only("pk", "uid", "author_id"), uid=series_uid
    )
    if series.author_id != request.user.pk:
        raise Http404

    if request.method == "POST":
        formset = CharacterFormSet(request.POST, prefix="characters")
        if formset.is_valid():
            name_list = [
                f.cleaned_data["name"]
                for f in formset
                if f.cleaned_data.get("name", "").strip()
            ]
            desc_list = [
                f.cleaned_data.get("description", "")
                for f in formset
                if f.cleaned_data.get("name", "").strip()
            ]
            if name_list:
                add_characters(series.pk, request.user.pk, name_list, desc_list)
                messages.success(request, f"{len(name_list)} character(s) added.")
            return redirect("series:series-detail", series_uid=series.uid)
    else:
        formset = CharacterFormSet(prefix="characters")

    return render(
        request,
        "series/character_form.html",
        {"series": series, "formset": formset, "editing": False},
    )


@login_required
def character_edit_view(request, series_uid, character_id):
    from series.models import Character

    series = get_object_or_404(
        Series.objects.only("pk", "uid", "author_id"), uid=series_uid
    )
    character = get_object_or_404(Character, pk=character_id, series_id=series.pk)

    if request.method == "POST":
        form = CharacterForm(request.POST)
        if form.is_valid():
            update_character(
                character_id=character.pk,
                user_id=request.user.pk,
                name=form.cleaned_data["name"],
                description=form.cleaned_data["description"],
            )
            messages.success(request, "Character updated.")
            return redirect("series:series-detail", series_uid=series.uid)
    else:
        form = CharacterForm(
            initial={"name": character.name, "description": character.description}
        )

    return render(
        request,
        "series/character_form.html",
        {"series": series, "form": form, "editing": True, "character": character},
    )


@login_required
def character_delete_view(request, series_uid, character_id):
    if request.method != "POST":
        return redirect("series:series-detail", series_uid=series_uid)
    series = get_object_or_404(
        Series.objects.only("pk", "uid", "author_id"), uid=series_uid
    )
    try:
        delete_character(character_id, request.user.pk)
        messages.success(request, "Character deleted.")
    except PermissionError:
        messages.error(request, "You don't have permission.")
    return redirect("series:series-detail", series_uid=series.uid)


# ---------------------------------------------------------------------------
# World view
# ---------------------------------------------------------------------------


@login_required
def world_edit_view(request, series_uid):
    # Only fetch series + world — no genres/characters prefetch needed
    series = get_object_or_404(
        Series.objects.select_related("world").only(
            "pk", "uid", "author_id", "name", "world"
        ),
        uid=series_uid,
    )
    if series.author_id != request.user.pk:
        raise Http404

    if request.method == "POST":
        form = WorldForm(request.POST)
        if form.is_valid():
            update_world(
                world_id=series.world.pk,
                user_id=request.user.pk,
                description=form.cleaned_data["description"],
            )
            messages.success(request, "World updated.")
            return redirect("series:series-detail", series_uid=series.uid)
    else:
        form = WorldForm(initial={"description": series.world.description})

    return render(request, "series/world_form.html", {"series": series, "form": form})
