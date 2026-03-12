# Remi — Architecture & Data Flow Audit

_Last updated: 2026-03-12_

---

## System Overview

Remi is a biographical interview system. A local LLM (qwen3:8b via Ollama) conducts
natural-language interviews with Tim, and an extraction pipeline turns what he says into
structured biographical data stored in SQLite + ChromaDB.

---

## Information Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       SWIFT MACOS APP                          │
│  ContentView → ChatViewModel → APIClient (HTTP to :8001)       │
└────────────────────────┬────────────────────────────────────────┘
                         │  POST /api/chat/stream  (NDJSON)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (:8001)                      │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐  │
│  │ RECEIVE  │──▶│ CLASSIFY │──▶│ STRATEGIZE │──▶│ RETRIEVE │  │
│  │ load msg │   │ rules    │   │ LLM call   │   │ DB query │  │
│  │ history  │   │ instant  │   │ ~2-4s      │   │ instant  │  │
│  └──────────┘   └──────────┘   └────────────┘   └──────────┘  │
│                                                       │         │
│                                                       ▼         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    RESPOND                              │   │
│  │  1. invoke_with_retry → full response (LLM, ~3-5s)     │   │
│  │  2. _validate_response → check length/hallucinations   │   │
│  │  3. retry if invalid (150 token budget)                │   │
│  │  4. fake-stream word-by-word to client (30ms/word)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│             ▼ (background, after stream)                        │
│  ┌──────────────────────┐   ┌─────────────────────────────┐   │
│  │      FINALIZE        │   │          EXTRACT            │   │
│  │  save messages to DB │   │  LLM extracts structured    │   │
│  │  vector store index  │   │  entities/facts from turn   │   │
│  └──────────────────────┘   └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SQLITE DATABASE                             │
│                                                                 │
│  conversations ──── messages (role, content, timestamp)        │
│       │                                                         │
│       └── provenance ──▶ entities ──── facts                   │
│                          (people,        (atomic bio facts,     │
│                           places,         category, era,        │
│                           orgs...)        confidence,           │
│                                           significance)         │
│                          entities ──── relationships            │
│                                         (directed edges)        │
│                                                                 │
│  coverage (per-category stats)                                  │
│  agent_state (key-value persistent state)                       │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│               CHROMADB (vector store)                           │
│  conversation exchanges → nomic-embed-text embeddings          │
│  used for RAG in STRATEGIZE (skipped for short/casual msgs)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Per-Node Breakdown

### RECEIVE
- Loads message history from `messages` table if `conversation_id` is provided
- Counts turns for context
- **No issues**

### CLASSIFY
- Rule-based regex (no LLM) — instant
- Returns: `intent`, `mood`, `is_correction`, `should_extract`
- Intents: `sharing | correcting | asking | greeting | casual`
- **Issue:** Intent doesn't feed into the STRATEGIZE LLM prompt content, only into its
  input state. The two used to run in parallel (classify result arrived too late).
  Now sequential — fixed.

### STRATEGIZE
- Loads: biography summary (cached), coverage gaps, unnamed people, pending verifications
- Optionally: vector RAG search (skipped for short/casual messages)
- LLM call → strategy text (1-2 sentences of interview instruction)
- **Issue:** The strategy is a text blob passed to the respond system prompt.
  The LLM has to interpret it. A structured agenda (JSON) would be more reliable.
- **Issue:** Coverage gaps drive strategy but the gaps list is category-level only.
  Remi knows "family is sparse" but not "we've never asked about Beryl's childhood".

### RETRIEVE
- Searches for person entities mentioned by name or family role in the user message
- Returns targeted fact block (e.g. "About Beryl: [3-4 facts]") instead of full dump
- **Issue:** Relationship data is NOT included. "Beryl is Tim's mother" won't appear
  unless it's a stored fact. The family graph structure is invisible to RESPOND.
- **Issue:** Only searches `person` entities. Place mentions (e.g. "Basildon") are
  not retrieved by name match.

### RESPOND
- Non-streaming invoke → validate → optional retry → fake-stream
- Validation: checks length (<80 words), hallucination phrases, question count
- **Issue:** Validation is purely syntactic. A response that's short and has one question
  but is still factually wrong (inventing details not in context) passes.
- **Issue:** The emergency fallback ("Tell me more — I'm listening") is generic.

### FINALIZE (background)
- Saves user + assistant messages to `messages` table
- Upserts to ChromaDB via `nomic-embed-text` embeddings
- **Issue:** Vector indexing silently fails if `nomic-embed-text` isn't installed in
  Ollama. The health check will still return OK. The RAG in STRATEGIZE returns
  nothing but no error is surfaced.
- **Issue:** The title field in `conversations` is never set. All conversations show
  as untitled in the sidebar.

### EXTRACT (background)
- LLM call on the last exchange → JSON with entities, facts, relationships
- **Critical issue:** Runs AFTER the response is sent. Facts from turn N are not
  available to turn N+1 if the user responds quickly.
- **Issue:** Duplicate detection uses exact string match. A rephrased fact creates a
  duplicate. There is no semantic deduplication.
- **Issue:** `mention_count` is never incremented. When an entity/fact is mentioned
  again, we detect it as "already exists" and skip — but the mention count stays at 1.
  This metric (useful for confidence boosting) is wasted.
- **Issue:** Relationship extraction is broken for cross-session entities.
  `entity_id_map` only contains entities created IN THIS EXTRACTION RUN. If Beryl
  was created in session 1 and her mother Elizabeth in session 2, the relationship
  "Beryl → mother → Elizabeth" won't be saved in session 2 because Beryl's ID
  isn't in `entity_id_map`.
- **Issue:** The `is_anchor` flag (for birth/death/marriage) is never set — always False.
- **Issue:** The `era` field (childhood/teens/adult etc.) is rarely populated.
  The prompt mentions it but doesn't emphasize it.

### CORRECT (triggered when `is_correction=True`)
- Loads ALL facts + entities into LLM context → identifies what to change
- **Issue:** Loading ALL facts scales badly. At 500+ facts this context window
  fills up and the LLM struggles to find the right IDs.
- **Issue:** A correction can only update `value`, `description`, or `name`.
  There is no way to correct `confidence`, `era`, `date_year`, `family_role`,
  or `category` through the CORRECT node.
- **Issue:** When an entity name is corrected (e.g. "Mum" → "Beryl"), existing
  facts that reference "Mum" in their `value` text are NOT updated. The fact might
  say "Tim's mother Mum preferred lighter conversations" forever.

---

## Database Schema Issues

### Facts table
| Issue | Impact |
|-------|--------|
| `mention_count` never incremented | Can't weight facts by how often they're confirmed |
| `is_anchor` never set | Birth/death/marriage not flagged as structural anchors |
| `era` rarely populated | Can't do chronological filtering or narrative ordering |
| No contradiction detection | "Born 1975" and "Born 1978" both stored, no flag |
| No versioning | Can't see what a fact was before correction |

### Entities table
| Issue | Impact |
|-------|--------|
| `mention_count` never incremented | Can't rank people by importance |
| `last_mentioned_at` never updated | Always shows creation time |
| `description` never updated after creation | Stays as initial brief extraction |
| Deduplication by exact name only | "Beryl" and "Beryl Jordan" = two entities |

### Relationships table
| Issue | Impact |
|-------|--------|
| Cross-session relationships not saved | Family graph fragmentary |
| No `label` or `description` field | Can't store nuance ("estranged", "close") |
| Bidirectional stored as flag, not two rows | Graph traversal more complex |

### Coverage table
| Issue | Impact |
|-------|--------|
| Updated on `add_fact` but NOT on `delete_fact` | Counts drift upward |
| `entity_count` column exists but never populated | Dead column |
| `era_coverage` JSON field never written | Can't see gaps by time period |

### Provenance table
| Issue | Impact |
|-------|--------|
| Only records creation, not updates | Can't audit who said what when |
| `message_id` field never populated | Can't trace a fact to a specific message |

---

## Data Lifecycle: A Fact About Beryl

```
1. Tim says: "my mum preferred not to talk about heavy things"
              │
              ▼
2. CLASSIFY   intent=sharing  should_extract=True
              │
              ▼
3. STRATEGIZE loads biography summary, decides follow-up approach
              │
              ▼
4. RETRIEVE   searches entities for "mum" → matches Beryl (family_role=mother)
              returns: "About Beryl: [known facts about her]"
              │
              ▼
5. RESPOND    generates: "That sounds like Beryl. Did she have particular topics
              she loved discussing?" — validates, fake-streams to client
              │
              ▼ (background)
6. FINALIZE   saves both messages to DB, indexes in ChromaDB
              │
              ▼ (background)
7. EXTRACT    LLM sees exchange, outputs:
              entity: {name: "Beryl", family_role: "mother", name_known: true}
              fact: {value: "Beryl preferred not to discuss heavy subjects",
                     category: "family", subject: "Beryl", significance: 3}
              │
              ▼
8. PERSIST    check: does "Beryl" exist? → search_entities("Beryl") → YES
              → entity_id_map["beryl"] = existing_id
              → check: fact already exists? LIKE search on first 50 chars → NO
              → add_fact(...) → fact saved with subject_entity_id = Beryl's ID
              → _invalidate_summary_cache()
```

**Gap at step 8:** If this is session 2 and Elizabeth (Beryl's mother) was introduced in
session 1, and the extract tries to add a relationship "Beryl → parent_child → Elizabeth",
Elizabeth's ID won't be in `entity_id_map` → relationship silently dropped.

---

## From a Biographer's Perspective: What's Missing

### 1. No interview agenda
Remi doesn't maintain a structured list of "things I want to know". Coverage categories
exist but they're too coarse. Remi should know:
- "I've never asked Tim about his education" (not just "education is sparse")
- "Tim mentioned his dad twice but I've never asked his name"
- "Tim seems to avoid talking about his relationship with his grandmother"

### 2. No temporal narrative structure
All facts exist in a flat table. A good biography has a timeline. The `era` and
`date_year` fields exist but are rarely populated, and they're not used to build
a chronological view of Tim's life for the LLM.

### 3. No contradiction detection
If Tim says he was born in London in session 1 and Manchester in session 5, both
facts are stored. No flag, no alert to Remi to reconcile.

### 4. No unanswered question tracking
If Remi asks "what happened with your grandmother?" and Tim changes the subject, that
should be noted as a deferred topic. Currently it's just forgotten.

### 5. Entity descriptions go stale
When Beryl is first extracted, her description might be "Tim's mother". Six sessions
later she's a richly described person, but the `description` field still says the same
thing because it's never updated from new facts.

### 6. The biography generation doesn't traverse the graph
`generate_biography()` dumps facts by category. It doesn't say "Beryl was Tim's mother,
and her mother was Elizabeth, and they had a complicated relationship". The relationships
table is completely ignored in biography generation.

---

## Recommended Fixes (Priority Order)

### P0 — Breaks functionality
1. **Cross-session relationship extraction**: when saving relationships, if entities
   aren't in `entity_id_map`, look them up in the DB by name. 1 extra DB query per
   relationship, completely fixes the family graph.

2. **Conversation title auto-generation**: Set `conversations.title` from the first
   user message (truncated). Currently all conversations are "untitled".

### P1 — Data quality
3. **Increment mention_count on re-mention**: In extract, when an entity/fact is
   found to already exist, call `UPDATE ... SET mention_count = mention_count + 1`
   instead of just skipping.

4. **Contradiction detection on add_fact**: Before saving, search for facts in the
   same category with similar predicates about the same subject. Flag conflicts for
   Remi to surface.

5. **Update entity description when new facts are added**: After extract saves new
   facts about an entity, rebuild the entity's description field from its top facts.

6. **Populate `era` field**: Add "era" to the EXTRACT_PROMPT examples. It's in the
   schema and in the prompt but barely used.

### P2 — Interview quality
7. **Structured interview gaps**: Instead of just "family: sparse", produce
   "Asked about: [Beryl's personality, Beryl's job]. Not yet asked: [name, birthplace,
   relationship with mother]". Feed this to STRATEGIZE.

8. **Deferred topic queue**: When Tim doesn't answer a question, record it in
   `agent_state` as a pending topic. Surface in STRATEGIZE.

9. **Semantic duplicate detection**: Before adding a fact, do a lightweight similarity
   check (word overlap or short embedding) against existing facts in the same category/
   subject. Would reduce fact pollution significantly.

10. **Relationship-aware RETRIEVE**: Include entity relationships in the focused context
    so the LLM knows "Beryl is Tim's mother, Elizabeth is Beryl's mother" without
    needing to read separate facts.
