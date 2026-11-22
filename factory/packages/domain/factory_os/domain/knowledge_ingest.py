"""Turn plain-text shop documents into a knowledge proposal.

The parser is deterministic and offline. It never writes ``shop_knowledge``.
A later confirm reuses ``PUT /api/knowledge``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from factory_os.domain.knowledge import sanitize_shop_pack

_MAX_CHARS = 50_000
_TEXT_SUFFIXES = {".txt", ".md", ".csv"}
_REJECT_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".zip",
}
_PROFILE_KEYS = ("vision", "mission", "objectives", "hours", "branches")
_POLICY_KEYS = ("returns", "exchanges", "cancel", "claims")
_KIND_BUCKET = {
    "faq": "faq",
    "identity": "vision",
    "hours": "hours",
    "policies": "policies",
}
_HEADERS = {
    "vision": "vision",
    "mision": "mission",
    "mission": "mission",
    "objetivos": "objectives",
    "objetivo": "objectives",
    "objectives": "objectives",
    "objective": "objectives",
    "horario": "hours",
    "horarios": "hours",
    "hours": "hours",
    "sucursal": "branches",
    "sucursales": "branches",
    "branches": "branches",
    "branch": "branches",
    "politicas": "policies",
    "policies": "policies",
    "policy": "policies",
    "condiciones": "policies",
    "condicion": "policies",
    "devoluciones": "returns",
    "devolucion": "returns",
    "cambios": "exchanges",
    "cambio": "exchanges",
    "cancelacion": "cancel",
    "faq": "faq",
    "faqs": "faq",
    "preguntas frecuentes": "faq",
    "preguntas": "faq",
}
_BRANCH_FIELDS = {
    "nombre": "name",
    "sucursal": "name",
    "name": "name",
    "horario": "hours",
    "horarios": "hours",
    "hours": "hours",
    "direccion": "address",
    "address": "address",
    "telefono": "phone",
    "phone": "phone",
    "celular": "phone",
}
_QA_LINE = re.compile(r"^(p|q|r|a|pregunta|respuesta)\s*[:：]\s*(.*)$", re.IGNORECASE)
_LIST_MARKER = re.compile(r"^[-*•]\s+")
_NEGATIVE = re.compile(
    r"\b(no se aceptan|no aceptamos|sin devoluciones|sin cambios|no hay)\b"
)
_POSITIVE = re.compile(r"\b(se aceptan|aceptamos|si|yes|true)\b")
_PURE_FLAG = re.compile(
    r"(si|no|yes|true|false|se aceptan|no se aceptan|aceptamos|no aceptamos|"
    r"sin devoluciones|sin cambios)"
)


def text_from_upload(
    filename: str | None,
    raw_bytes: bytes,
    content_type: str | None = None,
) -> str:
    """Decode a plain-text upload. PDF and Office files are rejected."""
    name = (filename or "").strip()
    suffix = Path(name).suffix.lower()
    media = (content_type or "").split(";", 1)[0].strip().lower()
    if suffix in _REJECT_SUFFIXES or _looks_like_binary_document(raw_bytes):
        raise ValueError("unsupported_document")
    allowed = suffix in _TEXT_SUFFIXES or media.startswith("text/")
    if media == "" and suffix in {".txt", ".md"}:
        allowed = True
    if not allowed:
        raise ValueError("unsupported_document")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("unsupported_document") from exc
    return text.replace("\x00", "")


def propose_shop_pack_from_text(text: str, *, kind: str | None = None) -> dict[str, Any]:
    """Map labeled plain text into a sanitize-ready shop pack fragment."""
    prepared = _prepare(text)
    hint = _normalize_kind(kind)
    blocks = _split_blocks(prepared)
    used: set[str] = set()
    faqs: list[dict[str, str]] = []
    profile_lines: dict[str, list[str]] = {
        "vision": [],
        "mission": [],
        "objectives": [],
        "hours": [],
    }
    branch_lines: list[str] = []
    policy_lines: dict[str, list[str]] = {
        "returns": [],
        "exchanges": [],
        "cancel": [],
        "policies": [],
    }

    for section, lines in blocks:
        remaining = _extract_faqs(lines, used, faqs)
        if section in profile_lines:
            profile_lines[section].extend(_clean_lines(remaining))
        elif section == "branches":
            branch_lines.extend(line.strip() for line in remaining if line.strip())
        elif section in policy_lines:
            policy_lines[section].extend(line.strip() for line in remaining if line.strip())
        elif section == "loose":
            _keep_loose(hint, remaining, profile_lines, policy_lines)

    raw: dict[str, Any] = {}
    profile: dict[str, Any] = {}
    for key in ("vision", "mission", "objectives"):
        if profile_lines[key]:
            profile[key] = profile_lines[key]
    hours = " ".join(profile_lines["hours"]).strip()
    if hours:
        profile["hours"] = hours
    branches = _parse_branches(branch_lines)
    if branches:
        profile["branches"] = branches
    if profile:
        raw["profile"] = profile
    policies = _policies_from_lines(policy_lines)
    if policies:
        raw["policies"] = policies
    if faqs:
        raw["faqs"] = faqs
    return _public_fragment(raw)


def _prepare(text: str) -> str:
    cleaned = str(text or "").replace("\x00", "")
    if len(cleaned) > _MAX_CHARS:
        cleaned = cleaned[:_MAX_CHARS]
    return cleaned.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_kind(kind: str | None) -> str | None:
    folded = _fold(kind or "")
    aliases = {
        "faq": "faq",
        "identidad": "identity",
        "identity": "identity",
        "horario": "hours",
        "horarios": "hours",
        "hours": "hours",
        "politicas": "policies",
        "policies": "policies",
    }
    return aliases.get(folded)


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    plain = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return plain.casefold().strip()


def _looks_like_binary_document(raw: bytes) -> bool:
    head = raw[:8]
    return head.startswith((b"%PDF", b"PK\x03\x04", b"\xd0\xcf\x11\xe0"))


def _split_blocks(text: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current = "loose"
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if any(line.strip() for line in buf):
            blocks.append((current, list(buf)))
        buf = []

    for line in text.split("\n"):
        if not (current == "branches" and _branch_field(line)):
            header = _match_header(line)
            if header is not None:
                flush()
                current, inline = header
                buf = [inline] if inline else []
                continue
        buf.append(line)
    flush()
    return blocks


def _match_header(line: str) -> tuple[str, str] | None:
    raw = re.sub(r"^#{1,6}\s*", "", line.strip()).strip("*_ ")
    if not raw:
        return None
    if ":" in raw or "：" in raw:
        label, rest = re.split(r"[:：]", raw, maxsplit=1)
        section = _HEADERS.get(_fold(label))
        if section is None or len(_fold(label).split()) > 3:
            return None
        return section, rest.strip()
    return _header_section(_fold(raw))


def _header_section(folded: str) -> tuple[str, str] | None:
    section = _HEADERS.get(folded)
    if section is None:
        return None
    return section, ""


def _branch_field(line: str) -> tuple[str, str] | None:
    raw = line.strip()
    if ":" not in raw and "：" not in raw:
        return None
    label, rest = re.split(r"[:：]", raw, maxsplit=1)
    key = _BRANCH_FIELDS.get(_fold(label))
    value = rest.strip()
    if key is None or not value:
        return None
    return key, value


def _keep_loose(
    hint: str | None,
    lines: list[str],
    profile_lines: dict[str, list[str]],
    policy_lines: dict[str, list[str]],
) -> None:
    bucket = _KIND_BUCKET.get(hint or "", "")
    cleaned = _clean_lines(lines)
    if bucket in {"vision", "mission", "objectives", "hours"}:
        profile_lines[bucket].extend(cleaned)
    elif bucket == "policies":
        policy_lines["policies"].extend(cleaned)


def _clean_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        text = _LIST_MARKER.sub("", line.strip())
        if text:
            cleaned.append(text)
    return cleaned


def _extract_faqs(
    lines: list[str],
    used: set[str],
    faqs: list[dict[str, str]],
) -> list[str]:
    remaining: list[str] = []
    index = 0
    while index < len(lines):
        parsed = _qa_prefix(lines[index])
        if parsed is not None and parsed[0] == "q":
            consumed, faq = _take_prefixed_faq(lines, index, parsed[1], used, len(faqs))
            if faq is not None:
                faqs.append(faq)
                index = consumed
                continue
        if _is_question_sentence(lines[index]):
            consumed, faq = _take_sentence_faq(lines, index, used, len(faqs))
            if faq is not None:
                faqs.append(faq)
                index = consumed
                continue
        remaining.append(lines[index])
        index += 1
    return remaining


def _qa_prefix(line: str) -> tuple[str, str] | None:
    match = _QA_LINE.match(line.strip())
    if match is None:
        return None
    label = _fold(match.group(1))
    if label in {"p", "q", "pregunta"}:
        return "q", match.group(2).strip()
    if label in {"r", "a", "respuesta"}:
        return "a", match.group(2).strip()
    return None


def _is_question_sentence(line: str) -> bool:
    text = line.strip()
    return "¿" in text and "?" in text and _qa_prefix(text) is None


def _take_prefixed_faq(
    lines: list[str],
    start: int,
    question: str,
    used: set[str],
    ordinal: int,
) -> tuple[int, dict[str, str] | None]:
    cursor = _skip_blank(lines, start + 1)
    if cursor >= len(lines):
        return start, None
    answer = _qa_prefix(lines[cursor])
    if answer is None or answer[0] != "a":
        return start, None
    parts = [answer[1]] if answer[1] else []
    cursor += 1
    while cursor < len(lines) and lines[cursor].strip():
        if _qa_prefix(lines[cursor]) or _is_question_sentence(lines[cursor]) or _match_header(lines[cursor]):
            break
        parts.append(lines[cursor].strip())
        cursor += 1
    if not question or not parts:
        return start, None
    return cursor, _faq_row(question, " ".join(parts), used, ordinal)


def _take_sentence_faq(
    lines: list[str],
    start: int,
    used: set[str],
    ordinal: int,
) -> tuple[int, dict[str, str] | None]:
    question = lines[start].strip()
    cursor = _skip_blank(lines, start + 1)
    parts: list[str] = []
    while cursor < len(lines) and lines[cursor].strip():
        if _is_question_sentence(lines[cursor]) or _match_header(lines[cursor]):
            break
        prefix = _qa_prefix(lines[cursor])
        if prefix is not None and prefix[0] == "q":
            break
        if prefix is not None and prefix[0] == "a":
            if prefix[1]:
                parts.append(prefix[1])
            cursor += 1
            continue
        parts.append(lines[cursor].strip())
        cursor += 1
    if not parts:
        return start, None
    return cursor, _faq_row(question, " ".join(parts), used, ordinal)


def _skip_blank(lines: list[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _faq_row(question: str, answer: str, used: set[str], ordinal: int) -> dict[str, str]:
    slug = _slug(question)
    if slug and slug not in used and slug != "__faq_list_replaces__":
        ident = slug
    else:
        number = ordinal + 1
        ident = f"faq-{number}"
        while ident in used or ident == "__faq_list_replaces__":
            number += 1
            ident = f"faq-{number}"
    used.add(ident)
    return {"id": ident, "question": question, "answer": answer}


def _slug(question: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _fold(question)).strip("-")
    return slug[:48].strip("-")


def _parse_branches(lines: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current: dict[str, str] = {}

    def flush() -> None:
        nonlocal current
        if any(current.values()):
            rows.append(
                {
                    "name": current.get("name", ""),
                    "hours": current.get("hours", ""),
                    "address": current.get("address", ""),
                    "phone": current.get("phone", ""),
                }
            )
        current = {}

    for line in lines:
        field = _branch_field(line)
        if field is not None:
            key, value = field
            if key == "name" and current.get("name"):
                flush()
            current[key] = value
            continue
        split = _split_branch_line(line)
        if split is not None:
            flush()
            rows.append(split)
            continue
        flush()
        rows.append({"name": line.strip(), "hours": "", "address": "", "phone": ""})
    flush()
    return rows


def _split_branch_line(line: str) -> dict[str, str] | None:
    if "|" in line:
        bits = [part.strip() for part in line.split("|")]
    elif "—" in line:
        bits = [part.strip() for part in line.split("—")]
    elif " - " in line:
        bits = [part.strip() for part in line.split(" - ")]
    else:
        return None
    bits = [bit for bit in bits if bit]
    if len(bits) < 2:
        return None
    row = {"name": "", "hours": "", "address": "", "phone": ""}
    for key, bit in zip(("name", "hours", "address", "phone"), bits, strict=False):
        row[key] = bit
    return row


def _policies_from_lines(groups: dict[str, list[str]]) -> dict[str, Any]:
    policies: dict[str, Any] = {}
    notes: list[str] = []
    for section in ("returns", "exchanges"):
        body = " ".join(groups[section]).strip()
        if not body:
            continue
        flag = _policy_flag(body)
        if flag is not None:
            policies[section] = flag
        if not _is_pure_flag(body):
            notes.append(body)
    cancel = " ".join(groups["cancel"]).strip()
    if cancel:
        policies["cancel"] = cancel
    general = " ".join(groups["policies"]).strip()
    if general:
        notes.append(general)
    if notes:
        policies["claims"] = "\n".join(notes)
    return policies


def _policy_flag(text: str) -> bool | None:
    folded = _fold(text).strip(" .")
    if _NEGATIVE.search(folded) or re.fullmatch(r"(no|false)", folded):
        return False
    if _POSITIVE.search(folded):
        return True
    return None


def _is_pure_flag(text: str) -> bool:
    return _PURE_FLAG.fullmatch(_fold(text).strip(" .")) is not None


def _present(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _public_fragment(raw: dict[str, Any]) -> dict[str, Any]:
    cleaned = sanitize_shop_pack(raw)
    fragment: dict[str, Any] = {}
    profile = {
        key: cleaned["profile"][key]
        for key in _PROFILE_KEYS
        if key in cleaned["profile"] and _present(cleaned["profile"][key])
    }
    if profile:
        fragment["profile"] = profile
    policies = {
        key: cleaned["policies"][key]
        for key in _POLICY_KEYS
        if key in cleaned["policies"] and _present(cleaned["policies"][key])
    }
    if policies:
        fragment["policies"] = policies
    faqs = []
    for row in cleaned["faqs"]:
        if not isinstance(row, dict):
            continue
        question = str(row.get("question") or "").strip()
        answer = str(row.get("answer") or "").strip()
        if not question and not answer:
            continue
        item: dict[str, str] = {
            "id": str(row.get("id") or ""),
            "question": question,
            "answer": answer,
        }
        category = str(row.get("category") or "").strip()
        if category:
            item["category"] = category
        faqs.append(item)
    if faqs:
        fragment["faqs"] = faqs
    return fragment
