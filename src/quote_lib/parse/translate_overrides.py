from __future__ import annotations

from quote_lib.parse.srt import ParsedEpisode

# Episodes with non-English subs (Archer S1 SYS release group).
# ISO 639-1 source language for MarianMT.
KNOWN_NON_ENGLISH: dict[tuple[int, int], str] = {
    (1, 4): "es",
    (1, 5): "es",
    (1, 6): "es",
    (1, 7): "es",
    (1, 8): "es",
    (1, 9): "es",
    (1, 10): "es",
}


def translation_source_lang(episode: ParsedEpisode) -> str | None:
    if episode.season is None or episode.episode is None:
        return None
    return KNOWN_NON_ENGLISH.get((episode.season, episode.episode))
