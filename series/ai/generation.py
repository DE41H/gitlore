from google.genai import types
from pgvector.django import CosineDistance

from series.ai.embedding import get_embeddings
from series.ai.gemini import client, generation_model
from series.models import Chapter, ChapterChunk, ChapterStatus, CharacterChunk
from series.models.world import WorldChunk
from series.services.tree import get_lineage

TEMPERATURE = 0.7


def generate_content(chapter_id: int) -> None:
    chapter = Chapter.objects.select_related("series").get(pk=chapter_id)
    if chapter.content:
        raise ValueError("Chapter already has content.")
    embedding = get_embeddings([chapter.prompt], task_type="retrieval_query")[0]
    context = get_context(
        chapter_id,
        chapter.series_id,  # pyright: ignore[reportAttributeAccessIssue]
        embedding,
    )
    system_prompt = (
        f'You are a creative writing assistant for "{chapter.series.name}", an ongoing collaborative story.\n\n'
        "Write a single chapter in response to the user's prompt. "
        "Use the context below to stay consistent with the established world, characters, and narrative. "
        "Write in vivid, immersive prose. Do not include chapter titles or headings.\n\n"
        f"{context}"
    )
    chapter.status = ChapterStatus.GENERATING
    chapter.save(update_fields=["status"])
    try:
        response = client.models.generate_content(
            model=generation_model,
            contents=chapter.prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt, temperature=TEMPERATURE
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty response.")
        chapter.content = response.text
        chapter.status = ChapterStatus.DONE
        chapter.save(update_fields=["content", "status"])
    except Exception:
        chapter.status = ChapterStatus.FAILED
        chapter.save(update_fields=["status"])
        raise


def get_context(chapter_id: int, series_id: int, embedding: list[float]) -> str:
    (
        relevant_character_notes,
        relevant_chapter_notes,
        previous_chapter_notes,
        world_notes,
    ) = ("", "", "", "")
    for cc in (
        CharacterChunk.objects.select_related("character")
        .filter(character__series_id=series_id)
        .annotate(distance=CosineDistance("embedding", embedding))
        .order_by("distance")
        .only("chunk", "character__name")[:10]
    ):
        relevant_character_notes += f"{cc.character.name}: {cc.chunk}\n"
    for cc in (
        ChapterChunk.objects.filter(chapter__series_id=series_id)
        .annotate(distance=CosineDistance("embedding", embedding))
        .order_by("distance")
        .only("chunk")[:10]
    ):
        relevant_chapter_notes += f"{cc.chunk}\n"
    for wc in (
        WorldChunk.objects.filter(world__series_id=series_id)
        .annotate(distance=CosineDistance("embedding", embedding))
        .order_by("distance")
        .only("chunk")[:5]
    ):
        world_notes += f"{wc.chunk}\n"
    for ch in get_lineage(chapter_id)[:-1][-3:]:
        previous_chapter_notes += f"{ch.content}\n\n"
    sections = []
    if world_notes:
        sections.append(f"## World\n{world_notes[:2000]}")
    if relevant_character_notes:
        sections.append(f"## Characters\n{relevant_character_notes[:3000]}")
    if previous_chapter_notes:
        sections.append(f"## Story So Far\n{previous_chapter_notes[:4000]}")
    if relevant_chapter_notes:
        sections.append(f"## Related Passages\n{relevant_chapter_notes[:2000]}")
    return "\n\n".join(sections)
