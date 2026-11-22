# Adoption notes — Conversation Knowledge

Source package adopted **22/09/2026**. Status: **indexed** (TK4 done).

Upstream docs in this folder (`README.md`, `CURSOR_INTEGRATION_SPEC.md`) describe the knowledge engineering. This file records how the package fits **this** repo after ADR-003.

## What was adopted

| File | Role here |
| --- | --- |
| `01_convrec_patterns.json` | Evidence / design. Provenance only. **Not indexed.** |
| `02_bitext_intent_taxonomy.json` | Intent vocabulary for eval / routing filters. **Not indexed.** |
| `03_adri_business_patterns.json` | Candidate playbook (input to curation). **Not indexed.** |
| `04_anti_patterns.json` | Raw anti-patterns (input to layering). **Not indexed.** |
| `05_playbook_curated.json` | **Canonical playbook** — 51 patterns, indexed in `conversation_playbook` (pgvector) + in-process `PlaybookIndex`. |
| `05_anti_patterns_layered.json` | Same 22 anti-patterns with `layer`: runtime / state_validation / quality_eval. **Not indexed** (enforced in code / eval). |
| `conversation_knowledge_bundle.json` | Bulk parity of 01–04 only. |
| `manifest.json` | Checksums, licenses, adoption status. |

## Curation rules (TK3)

1. Base = 03 (46). On the 7 exact intent overlaps with 01, **Adri wins**; ConvRec id goes in `supersedes` and useful behavior/avoid lines are merged.
2. From 01, keep only unique Closet-useful intents: `product_discovery`, `positive_feedback`, `negative_feedback`, `conversation_closure`, `conversation_continuity`. Drop brand/attribute/recommendation/feature/off_topic (covered or low fit).
3. Every pattern has `next_action` ∈ runtime enum, `skill` ∈ `ADRI_SKILLS`, `allowed_tools` ⊆ `{catalog.search, cart.add, order.create}`, `knowledge_sources` ⊆ `{catalog, shop_knowledge, working_state}`, `capability` ∈ `{adri, shop_answer_only, handoff, escalate}`.
4. Closet gates: no reservation WRITE; returns/exchanges → `shop_answer_only` from `shop_knowledge`; order tracking → `handoff`; payment QR is Cobros, not Adri.
5. `example_is_not_fact: true` always — examples never become catalog/policy facts.

## Indexing rules (TK4)

1. Table `conversation_playbook` is **separate** from `product_embeddings` and `shop_knowledge`.
2. Embed blob = intent + situation + goal + signals + behavior + avoid + next_action/skill/capability. **Never** `example_customer_message`.
3. Max **2** positive hits per turn (`PLAYBOOK_MAX_HITS`), injected as `playbook_hints` into SalesDecision propose context.
4. Hints are labeled behavior-only; they do not supply price, stock, or policy.
5. Seed runs in `open_postgres_shop` via `seed_conversation_playbook`. Pytest uses hashed vectors of the same dimension.

## What is still out of scope

- No intent classifier that runs **before** the LLM.
- Anti-patterns are not RAG chunks.
- Playbook is optional READ, never a parallel sales script.

## ADR-003 flow

```text
LLM seller (SalesDecision)
  → may see up to 2 playbook hints + catalog / shop facts
  → runtime retrieves curated patterns (behavior) and catalog (facts)
  → LLM decides and drafts
  → WRITE goes through Tool Runtime
```

## Separation that must not break

| Store | Answers |
| --- | --- |
| Business RAG (`product_embeddings`, `shop_knowledge`, `agent_catalog_read`) | What Closet sells / policies / stock / price |
| Conversation playbook (`conversation_playbook` ← `05_playbook_curated.json`) | How to handle a sales situation |
