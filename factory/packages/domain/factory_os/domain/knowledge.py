"""Tenant business knowledge: profile, FAQs, policies, voice.

Catalog price/stock still come from agent_catalog_read. Empty socials/location
are omitted — never invented. Temporal live promos are not stored here.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.seed import tokenize

_GARMENT = frozenset(
    {
        "blusa",
        "blusas",
        "vestido",
        "vestidos",
        "falda",
        "faldas",
        "short",
        "shorts",
        "jean",
        "jeans",
        "pantalon",
        "pantalones",
        "polera",
        "poleras",
        "top",
        "tops",
        "conjunto",
        "chaqueta",
        "chaquetas",
    }
)
_CATALOG_FAQ = frozenset({"Precios", "Productos"})
# Function words that must not decide FAQ hits (WA typo: "que"+"una" → tiktok-buy).
_FAQ_STOP = frozenset(
    {
        "a",
        "al",
        "buy",
        "como",
        "con",
        "de",
        "del",
        "el",
        "en",
        "es",
        "esta",
        "este",
        "esto",
        "hay",
        "la",
        "las",
        "le",
        "lo",
        "los",
        "me",
        "mi",
        "o",
        "para",
        "por",
        "puedo",
        "puede",
        "que",
        "se",
        "si",
        "sin",
        "su",
        "te",
        "tu",
        "un",
        "una",
        "unas",
        "unos",
        "vi",
        "y",
        "ya",
    }
)


def shop_seed_path() -> Path:
    """Live shop card. CATALOG_SEED=cafe loads the cafeteria; anything else stays Closet."""
    filename = (
        "shop_cafe.json"
        if os.environ.get("CATALOG_SEED", "").strip().lower() == "cafe"
        else "shop_closet.json"
    )
    here = Path(__file__).resolve()
    for parent in here.parents:
        path = parent / "db" / "seeds" / filename
        if path.exists():
            return path
    raise FileNotFoundError(filename)


@lru_cache(maxsize=1)
def load_shop_pack() -> dict[str, Any]:
    return json.loads(shop_seed_path().read_text(encoding="utf-8"))


def shop_pack_for(tenant_id: UUID) -> dict[str, Any] | None:
    pack = load_shop_pack()
    if str(pack.get("tenant_id") or "") != str(tenant_id) and tenant_id != PILOT_TENANT_ID:
        return None
    return pack


_FORBIDDEN_FACT_KEYS = frozenset(
    {"price", "unit_price", "stock", "payment_status", "confirmed", "provider_ref"}
)


def _active_pack(tenant_id: UUID | None, pack: dict[str, Any] | None) -> dict[str, Any] | None:
    if pack is not None:
        return pack
    return shop_pack_for(tenant_id or PILOT_TENANT_ID)


def _strip_forbidden(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_forbidden(item)
            for key, item in value.items()
            if key not in _FORBIDDEN_FACT_KEYS
        }
    if isinstance(value, list):
        return [_strip_forbidden(item) for item in value]
    return value


# A FAQ list without this id upserts by id. Including it replaces the stored list.
# The API merges once and the store merges that result again: the first pass keeps
# the marker so the second pass still replaces, then drops the marker.
_FAQ_REPLACE = "__faq_list_replaces__"
_TONES = frozenset({"cercana", "directa", "critica", "formal"})
_BRANCH_FIELDS = ("name", "hours", "address", "phone")
_TONE_FOLDS = str.maketrans({"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u"})


class _SanitizedPack(dict[str, Any]):
    """Dict already returned by sanitize_shop_pack. Not a stored field."""


def _text_lines(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip()]
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, str):
                lines.extend(_text_lines(item))
        return lines
    return []


def _channels(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return _text_lines(value)


def _branches(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        row = {key: str(item.get(key) or "").strip() for key in _BRANCH_FIELDS}
        if any(row.values()):
            rows.append(row)
    return rows


def _fold_tone(value: Any) -> str:
    folded = str(value or "").strip().lower().translate(_TONE_FOLDS)
    return folded if folded in _TONES else ""


def _normalize_profile(raw: dict[str, Any]) -> dict[str, Any]:
    profile = dict(raw)
    for key in ("vision", "mission", "objectives"):
        if key in profile:
            profile[key] = _text_lines(profile[key])
    if "branches" in profile:
        profile["branches"] = _branches(profile["branches"])
    if "channels" in profile:
        profile["channels"] = _channels(profile["channels"])
    return profile


def _normalize_voice(raw: dict[str, Any]) -> dict[str, Any]:
    voice = dict(raw)
    if "tone" in voice:
        tone = _fold_tone(voice.get("tone"))
        if tone:
            voice["tone"] = tone
        else:
            voice.pop("tone", None)
    for key in ("traits", "words_use", "words_avoid", "example_replies"):
        if key in voice:
            voice[key] = _text_lines(voice[key])
    if "address" in voice and voice["address"] is not None:
        voice["address"] = str(voice["address"]).strip()
    if "emojis" in voice and voice["emojis"] is not None:
        voice["emojis"] = str(voice["emojis"]).strip()
    return voice


def _normalize_vocabulary(raw: dict[str, Any]) -> dict[str, Any]:
    vocab = dict(raw)
    if "item" in vocab and vocab["item"] is not None:
        vocab["item"] = str(vocab["item"]).strip()
    return vocab


def _normalize_faqs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _plain_pack(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": dict(pack.get("profile") or {}),
        "policies": dict(pack.get("policies") or {}),
        "voice": dict(pack.get("voice") or {}),
        "faqs": _normalize_faqs(pack.get("faqs")),
        "vocabulary": dict(pack.get("vocabulary") or {}),
    }


def _has_faq_replace_marker(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    faqs = raw.get("faqs")
    if not isinstance(faqs, list):
        return False
    return any(isinstance(row, dict) and str(row.get("id") or "") == _FAQ_REPLACE for row in faqs)


def sanitize_shop_pack(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Keep business knowledge. Drop price, stock, and payment confirmation."""
    cleaned = _strip_forbidden(dict(raw or {}))
    return _SanitizedPack(
        {
            "profile": _normalize_profile(dict(cleaned.get("profile") or {})),
            "policies": dict(cleaned.get("policies") or {}),
            "voice": _normalize_voice(dict(cleaned.get("voice") or {})),
            "faqs": _normalize_faqs(cleaned.get("faqs")),
            "vocabulary": _normalize_vocabulary(dict(cleaned.get("vocabulary") or {})),
        }
    )


def merge_shop_pack(base: dict[str, Any] | None, patch: dict[str, Any] | None) -> dict[str, Any]:
    explicit_faqs = isinstance(patch, dict) and not isinstance(patch, _SanitizedPack) and "faqs" in patch
    replace_stored = _has_faq_replace_marker(patch)
    current = _plain_pack(sanitize_shop_pack(base))
    incoming = _plain_pack(sanitize_shop_pack(patch))
    for key in ("profile", "policies", "voice", "vocabulary"):
        current[key].update(incoming[key])
    kept = [row for row in incoming["faqs"] if str(row.get("id") or "") != _FAQ_REPLACE]
    if replace_stored:
        if isinstance(patch, _SanitizedPack):
            current["faqs"] = kept
        else:
            current["faqs"] = [*kept, {"id": _FAQ_REPLACE, "question": "", "answer": ""}]
    elif explicit_faqs or kept:
        by_id = {
            str(row.get("id") or ""): row
            for row in current["faqs"]
            if str(row.get("id") or "") != _FAQ_REPLACE
        }
        for row in kept:
            by_id[str(row.get("id") or "")] = row
        current["faqs"] = list(by_id.values())
    return current


def item_word(pack: dict[str, Any] | None) -> str:
    word = str(((pack or {}).get("vocabulary") or {}).get("item") or "prenda").strip()
    return word or "prenda"


def shop_label(pack: dict[str, Any] | None) -> str:
    name = str(((pack or {}).get("profile") or {}).get("name") or "Closet").strip()
    if name == "Authentic Closet":
        return "Closet"
    return name or "Closet"


def item_plural(pack: dict[str, Any] | None) -> str:
    """Plural of the customer item noun. The default stays 'prendas'."""
    word = item_word(pack)
    if word.endswith("s"):
        return word
    return f"{word}s"


def spoken_shop_name(pack: dict[str, Any] | None) -> str:
    """Full profile name for greetings and thanks.

    A missing card keeps 'Authentic Closet'. shop_label shortens that same
    name to 'Closet' for the short handover notice.
    """
    name = str(((pack or {}).get("profile") or {}).get("name") or "").strip()
    return name or "Authentic Closet"


_FICHE_WORD_BUDGET = 120
_CLOSET_CONDUCT = (
    "Amable y cercana",
    "Directa con lo que está en FACTS",
    "Una pregunta a la vez",
)


def _one_line(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:")
    return clipped or text[:limit].rstrip()


def _voice_bits(value: Any, limit: int) -> list[str]:
    bits: list[str] = []
    for line in _text_lines(value):
        cleaned = " ".join(line.split())
        if cleaned:
            bits.append(cleaned)
        if len(bits) >= limit:
            break
    return bits


def _csv_crumb(items: list[str]) -> str:
    parts = [" ".join(item.replace(",", " ").split()) for item in items]
    return ", ".join(part for part in parts if part)


def _examples_crumb(items: list[str]) -> str:
    parts: list[str] = []
    for item in items:
        cleaned = _one_line(item.replace("|", "/"), 80)
        if cleaned:
            parts.append(cleaned)
    return "|".join(parts)


def _identity_text(profile: dict[str, Any], limit: int) -> str:
    summary = " ".join(str(profile.get("summary") or "").split())
    differentiator = " ".join(str(profile.get("differentiator") or "").split())
    if summary:
        return _one_line(summary, limit)
    if differentiator:
        return _one_line(differentiator, limit)
    return ""


def _is_closet_seed_pack(pack: dict[str, Any]) -> bool:
    profile = pack.get("profile") or {}
    if not isinstance(profile, dict) or not profile.get("hours"):
        return False
    seed_profile = load_shop_pack().get("profile") or {}
    return (
        str(profile.get("name") or "") == str(seed_profile.get("name") or "")
        and str(profile.get("hours") or "") == str(seed_profile.get("hours") or "")
        and str(profile.get("payment") or "") == str(seed_profile.get("payment") or "")
    )


def _conduct_lines(pack: dict[str, Any], voice: dict[str, Any]) -> list[str]:
    traits = _voice_bits(voice.get("traits"), 3)
    if traits:
        return traits
    if _is_closet_seed_pack(pack):
        return list(_CLOSET_CONDUCT)
    return []


def _trim_fiche(lines: list[str]) -> str:
    while lines and len("\n".join(lines).split()) > _FICHE_WORD_BUDGET:
        if any(line.startswith("- ") for line in lines):
            for index in range(len(lines) - 1, -1, -1):
                if lines[index].startswith("- "):
                    del lines[index]
                    break
            if lines and lines[-1].startswith("EJEMPLOS DE TONO"):
                lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def brand_fiche(pack: dict[str, Any] | None) -> str:
    """Short brand block for Adri. Empty when the pack has no stored voice or identity."""
    if not pack:
        return ""
    profile = pack.get("profile") if isinstance(pack.get("profile"), dict) else {}
    voice = pack.get("voice") if isinstance(pack.get("voice"), dict) else {}
    lines: list[str] = []
    identity = _identity_text(profile, 160)
    if identity:
        lines.append(f"IDENTIDAD: {identity}")
    conduct = _conduct_lines(pack, voice)
    if conduct:
        lines.append("CÓMO ACTÚAS:")
        lines.extend(conduct)
    tone = _fold_tone(voice.get("tone"))
    address = " ".join(str(voice.get("address") or "").split())
    emojis = " ".join(str(voice.get("emojis") or "").split())
    words_use = _voice_bits(voice.get("words_use"), 6)
    words_avoid = _voice_bits(voice.get("words_avoid"), 6)
    examples = _voice_bits(voice.get("example_replies"), 4)
    if not any((identity, conduct, tone, words_use, words_avoid, examples)):
        return ""
    speak_bits: list[str] = []
    if address:
        speak_bits.append(f"trato de {address}")
    if tone:
        speak_bits.append(f"tono {tone}")
    if emojis:
        speak_bits.append(f"emojis {emojis}")
    vocab_bits: list[str] = []
    if words_use:
        vocab_bits.append("Usá: " + ", ".join(words_use))
    if words_avoid:
        vocab_bits.append("Evitá: " + ", ".join(words_avoid))
    speak = "; ".join(speak_bits)
    if vocab_bits:
        speak = f"{speak}. {' '.join(vocab_bits)}." if speak else f"{' '.join(vocab_bits)}."
    if speak:
        lines.append(f"CÓMO HABLAS: {speak}")
    if examples:
        lines.append("EJEMPLOS DE TONO (solo tono; no copies datos ni precios):")
        lines.extend(f"- {_one_line(example, 90)}" for example in examples)
    return _trim_fiche(lines)


def _brand_card_lines(profile: dict[str, Any], voice: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    identity = _identity_text(profile, 80)
    if identity:
        rows.append(f"identity={identity}")
    tone = _fold_tone(voice.get("tone"))
    if tone:
        rows.append(f"tone={tone}")
    traits = _csv_crumb(_voice_bits(voice.get("traits"), 3))
    if traits:
        rows.append(f"traits={traits}")
    words_use = _csv_crumb(_voice_bits(voice.get("words_use"), 8))
    if words_use:
        rows.append(f"words_use={words_use}")
    words_avoid = _csv_crumb(_voice_bits(voice.get("words_avoid"), 8))
    if words_avoid:
        rows.append(f"words_avoid={words_avoid}")
    examples = _examples_crumb(_voice_bits(voice.get("example_replies"), 2))
    if examples:
        rows.append(f"examples={examples}")
    return rows


def pack_for_tenant(store: Any, tenant_id: UUID | None) -> dict[str, Any] | None:
    """Saved shop card. A missing store or card stays None so copy helpers default."""
    if store is None or tenant_id is None:
        return None
    getter = getattr(store, "get_shop_knowledge", None)
    if not callable(getter):
        return None
    return getter(tenant_id)


def compact_shop_card(tenant_id: UUID | None = None, pack: dict[str, Any] | None = None) -> str:
    pack = _active_pack(tenant_id, pack)
    if not pack:
        return ""
    profile = pack.get("profile") or {}
    policies = pack.get("policies") or {}
    voice = pack.get("voice") or {}
    tone = _fold_tone(voice.get("tone"))
    voice_line = f"voice={voice.get('address')} emojis={voice.get('emojis')}"
    if tone:
        voice_line = f"{voice_line} tone={tone}"
    lines = [
        f"shop={profile.get('name')}",
        f"hours={profile.get('hours')} payment={profile.get('payment')} currency={profile.get('currency')}",
        f"delivery={profile.get('delivery_zones')} pickup=no eta_sc={profile.get('eta_santa_cruz')}",
        f"returns=no exchanges=no pay_window_min={policies.get('payment_window_min')} claims={profile.get('contact_phone')}",
        voice_line,
        "no inventar precio/stock/promo ni redes o ubicación no registradas",
    ]
    tiktok = str(profile.get("tiktok") or "").strip()
    if tiktok:
        lines.insert(2, f"tiktok={tiktok}")
    faq_ids = [str(row.get("id") or "").strip() for row in (pack.get("faqs") or [])]
    faq_ids = [item for item in faq_ids if item and item != _FAQ_REPLACE]
    if faq_ids:
        lines.append("faqs=" + ",".join(faq_ids))
    vocab = str(((pack.get("vocabulary") or {}).get("item") or "")).strip()
    if vocab:
        lines.append(f"item={vocab}")
    if isinstance(profile, dict) and isinstance(voice, dict):
        lines.extend(_brand_card_lines(profile, voice))
    return "\n".join(lines)


def match_faq(
    text: str, tenant_id: UUID | None = None, pack: dict[str, Any] | None = None
) -> dict[str, str] | None:
    pack = _active_pack(tenant_id, pack)
    if not pack:
        return None
    tokens = tokenize(text)
    meaningful = tokens - _FAQ_STOP
    if not meaningful:
        return None
    best: dict[str, str] | None = None
    best_score = 0
    for row in pack.get("faqs") or []:
        hay = tokenize(str(row.get("question") or "")) | tokenize(str(row.get("category") or ""))
        hay |= tokenize(str(row.get("id") or "").replace("-", " "))
        hay_m = hay - _FAQ_STOP
        score = len(meaningful & hay_m)
        if {"delivery", "envio", "envios"} & tokens and row.get("id") == "delivery":
            score += 3
        if {"pago", "pagar", "qr"} & tokens and row.get("id") == "pay":
            score += 3
        if {"tiktok", "live"} & tokens and row.get("id") in {"where", "tiktok-buy"}:
            score += 2
        if {"cuenta", "link", "perfil", "pagina", "usuario"} & tokens and row.get("id") == "where":
            score += 3
        # TikTok Live FAQ only when the client mentions live/tiktok — not "una blusa".
        if row.get("id") == "tiktok-buy" and not ({"tiktok", "live"} & tokens):
            continue
        if {"devolucion", "devoluciones", "cambio", "cambios"} & tokens:
            continue
        if score > best_score:
            best_score = score
            best = {
                "id": str(row.get("id") or ""),
                "category": str(row.get("category") or ""),
                "question": str(row.get("question") or ""),
                "answer": str(row.get("answer") or ""),
            }
    if best_score < 2 or best is None:
        return None
    return best


def policy_answer(
    text: str, tenant_id: UUID | None = None, pack: dict[str, Any] | None = None
) -> str | None:
    pack = _active_pack(tenant_id, pack)
    if not pack:
        return None
    tokens = tokenize(text)
    policies = pack.get("policies") or {}
    if {"devolucion", "devoluciones", "cambio", "cambios"} & tokens:
        custom = str(policies.get("returns_answer") or "").strip()
        if custom:
            return custom
        if policies.get("returns") is False:
            return "No aceptamos devoluciones ni cambios. Si hay un reclamo, escribinos o llamá al 78629237."
        return None
    if {"cancel", "cancelar", "cancelacion"} & tokens:
        return str(policies.get("cancel") or "")
    if {"garantia", "garantías", "garantias"} & tokens:
        return str(policies.get("warranty") or "")
    if {"reclamo", "reclamos"} & tokens:
        return str(policies.get("claims") or "")
    return None


def is_shop_question(
    text: str, tenant_id: UUID | None = None, pack: dict[str, Any] | None = None
) -> bool:
    from factory_os.domain.seed import product_code_tokens

    # Named catalog/live product code → commercial search, not shop FAQ
    # (e.g. "el código del live es pago1" must not hit the TikTok Live FAQ).
    if product_code_tokens(text):
        return False
    if policy_answer(text, tenant_id, pack):
        return True
    faq = match_faq(text, tenant_id, pack)
    if not faq:
        return False
    tokens = tokenize(text)
    # Garment browse ("busco blusa") is catalog discovery, not shop FAQ.
    if tokens & _GARMENT and faq.get("category") in _CATALOG_FAQ:
        return False
    if tokens & _GARMENT and faq.get("id") in {"tiktok-buy", "availability"} and not (
        {"tiktok", "live"} & tokens
    ):
        return False
    return True


def shop_reply(
    text: str, tenant_id: UUID | None = None, pack: dict[str, Any] | None = None
) -> str | None:
    policy = policy_answer(text, tenant_id, pack)
    if policy:
        return policy
    faq = match_faq(text, tenant_id, pack)
    if faq:
        return faq["answer"]
    return None
