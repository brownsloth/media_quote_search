from __future__ import annotations

import time
from dataclasses import dataclass

from quote_lib.parse.clean import clean_cue_text
from quote_lib.parse.srt import ParsedEpisode
from quote_lib.parse.translate_overrides import translation_source_lang

# Helsinki MarianMT — offline after first model download.
MODEL_BY_PAIR: dict[tuple[str, str], str] = {
    ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
    ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
    ("de", "en"): "Helsinki-NLP/opus-mt-de-en",
}


def _log(msg: str, *, verbose: bool) -> None:
    if verbose:
        print(msg, flush=True)


def _pick_device(requested: str | None) -> str:
    import torch

    if requested and requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class TranslateOptions:
    verbose: bool = True
    batch_size: int = 32
    device: str = "auto"
    max_new_tokens: int = 128


class MarianTranslator:
    def __init__(self, options: TranslateOptions | None = None) -> None:
        self.options = options or TranslateOptions()
        self._loaded: dict[tuple[str, str], tuple[object, object, str]] = {}

    def _get(self, src: str, tgt: str):
        key = (src, tgt)
        if key not in self._loaded:
            from transformers import MarianMTModel, MarianTokenizer

            model_name = MODEL_BY_PAIR.get(key)
            if model_name is None:
                raise ValueError(f"No Marian model configured for {src}->{tgt}")

            device = _pick_device(self.options.device)
            _log(f"    loading MarianMT {model_name} -> {device} (first run downloads ~300MB) ...", verbose=self.options.verbose)
            t0 = time.time()
            tok = MarianTokenizer.from_pretrained(model_name)
            _log(f"    tokenizer ready ({time.time() - t0:.1f}s)", verbose=self.options.verbose)
            model = MarianMTModel.from_pretrained(model_name)
            model.eval()
            model.to(device)
            _log(f"    model ready on {device} ({time.time() - t0:.1f}s total)", verbose=self.options.verbose)
            self._loaded[key] = (tok, model, device)
        return self._loaded[key]

    def translate_batch(
        self,
        texts: list[str],
        src: str,
        tgt: str = "en",
        *,
        batch_size: int | None = None,
        label: str = "",
    ) -> list[str]:
        if not texts:
            return []

        opts = self.options
        batch_size = batch_size or opts.batch_size
        tok, model, device = self._get(src, tgt)
        import torch

        out: list[str] = []
        total = len(texts)
        total_batches = (total + batch_size - 1) // batch_size
        prefix = f"    {label} " if label else "    "

        _log(f"{prefix}translating {total} cues in {total_batches} batches (size={batch_size}) ...", verbose=opts.verbose)
        t0 = time.time()

        for batch_idx, start in enumerate(range(0, total, batch_size), start=1):
            batch = texts[start : start + batch_size]
            encoded = tok(batch, return_tensors="pt", padding=True, truncation=True, max_length=256)
            encoded = {k: v.to(device) for k, v in encoded.items()}
            with torch.no_grad():
                generated = model.generate(
                    **encoded,
                    max_new_tokens=opts.max_new_tokens,
                    num_beams=1,
                    do_sample=False,
                )
            out.extend(tok.batch_decode(generated, skip_special_tokens=True))

            if opts.verbose and (
                batch_idx == 1 or batch_idx == total_batches or batch_idx % 5 == 0
            ):
                done = min(start + batch_size, total)
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                _log(
                    f"{prefix}batch {batch_idx}/{total_batches} — {done}/{total} cues "
                    f"({rate:.0f} cues/s, {elapsed:.0f}s elapsed)",
                    verbose=True,
                )

        _log(f"{prefix}done ({time.time() - t0:.1f}s)", verbose=opts.verbose)
        return out


_TRANSLATOR: MarianTranslator | None = None
_TRANSLATOR_OPTS: TranslateOptions | None = None


def get_translator(options: TranslateOptions | None = None) -> MarianTranslator:
    global _TRANSLATOR, _TRANSLATOR_OPTS
    opts = options or TranslateOptions()
    if _TRANSLATOR is None or _TRANSLATOR_OPTS != opts:
        _TRANSLATOR = MarianTranslator(opts)
        _TRANSLATOR_OPTS = opts
    return _TRANSLATOR


def translate_episode(
    episode: ParsedEpisode,
    src_lang: str,
    target_lang: str = "en",
    *,
    options: TranslateOptions | None = None,
    label: str = "",
) -> ParsedEpisode:
    """Translate dialogue cues from src_lang to target_lang."""
    opts = options or TranslateOptions()
    episode.detected_language = src_lang
    if src_lang == target_lang:
        return episode

    pair = (src_lang, target_lang)
    if pair not in MODEL_BY_PAIR:
        episode.parse_errors.append(f"translation_skipped: no model for {src_lang}->{target_lang}")
        return episode

    dialogue_indices: list[int] = []
    dialogue_texts: list[str] = []
    for i, cue in enumerate(episode.cues):
        if cue.is_watermark or not cue.text_raw.strip():
            continue
        dialogue_indices.append(i)
        dialogue_texts.append(cue.text_raw)

    if not dialogue_texts:
        _log(f"    {label}no dialogue cues to translate", verbose=opts.verbose)
        return episode

    translator = get_translator(opts)
    translated = translator.translate_batch(
        dialogue_texts,
        src=src_lang,
        tgt=target_lang,
        label=label,
    )

    for idx, english in zip(dialogue_indices, translated):
        cue = episode.cues[idx]
        cue.text_original = cue.text_raw
        cue.text_raw = english
        cue.text_clean = clean_cue_text(english, for_embed=True)

    episode.was_translated = True
    return episode


def translate_known_episodes(
    episode: ParsedEpisode,
    target_lang: str = "en",
    *,
    options: TranslateOptions | None = None,
) -> ParsedEpisode:
    """Translate only episodes listed in KNOWN_NON_ENGLISH (no langdetect)."""
    src_lang = translation_source_lang(episode)
    if src_lang is None:
        return episode
    label = ""
    if episode.season is not None and episode.episode is not None:
        label = f"S{episode.season:02d}E{episode.episode:02d}: "
    return translate_episode(episode, src_lang=src_lang, target_lang=target_lang, options=options, label=label)
