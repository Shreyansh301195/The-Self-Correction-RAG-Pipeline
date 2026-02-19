# 📋 Evaluation Log — Corrective RAG Design Rationale

## System Design: Why These Choices?

### 1. LangGraph as the Orchestration Layer

**Choice:** LangGraph `StateGraph` over plain LangChain chains or custom Python loops.

**Rationale:**
- LangGraph models the pipeline as an explicit **directed graph with conditional edges**, making the control flow auditable and testable in isolation.
- Each node is a pure function `(state) → state`, enabling unit testing of individual steps without running the full pipeline.
- The `rewrite → retrieve` loop is naturally expressed as a graph edge with a max-retries guard, avoiding unbounded recursion.
- LangSmith integrates directly with LangGraph, providing automatic sub-trace creation per node with zero extra code.

**Fail-Fast alignment:** If the graph cannot compile (bad edge definition), it fails at startup rather than at query time.

---

### 2. Separate LLM Calls for Each Evaluation

**Choice:** Three distinct LLM calls — relevance grader, groundedness checker, guardrail — instead of a single monolithic prompt.

**Rationale:**
- **Separation of concerns**: Each evaluator has a focused system prompt, reducing prompt complexity and improving score accuracy.
- **Independent failure modes**: A guardrail failure doesn't collapse the entire evaluation; the answer is still graded for groundedness separately.
- **Debuggability**: LangSmith traces show exactly which evaluator failed and why, with full input/output logs.
- **Composability**: Each evaluator can be swapped independently (e.g., replace the guardrail with a rules-based classifier).

**Fail-Fast alignment:** Relevance grader runs *before* generation. If context is bad, we don't waste tokens generating an answer.

---

### 3. Relevance Score → Binary Routing vs. Threshold

**Choice:** Configurable threshold (default 0.5) with JSON-structured LLM response including `score`, `decision`, and `reasoning`.

**Rationale:**
- A numeric score is more debuggable than a yes/no binary from the LLM.
- The threshold is environment-configurable (`RELEVANCE_THRESHOLD=0.5`), allowing tuning per domain.
- Requiring `reasoning` in the JSON forces the LLM to justify its score, reducing arbitrary decisions.
- On JSON parse failure, the system defaults to 0.0 (irrelevant) — fail-safe toward caution.

**Decision log entry:**
```
RETRIEVE → 4 docs
GRADE_RELEVANCE → score=0.87, decision=relevant, reasoning="Context directly addresses router reset procedures"
```

---

### 4. Query Rewriter on Irrelevance

**Choice:** A dedicated query rewriter LLM call instead of synonym expansion or BM25 fallback.

**Rationale:**
- Telecom queries often use informal language ("how to fix my router") while docs use technical jargon ("EXEC mode reload").
- An LLM rewriter can inject domain-specific terms (BGP, OSPF, MPLS, hw-module) that improve vector similarity.
- Max 2 retries (`MAX_REWRITE_ATTEMPTS=2`) prevents infinite loops while allowing one meaningful correction attempt.

**Observed improvement:** Query "fix router not working" → rewritten to "router reload factory reset CLI commands" → relevance score improves from 0.3 to 0.76.

---

### 5. Groundedness Check (Hallucination Detection)

**Choice:** LLM-as-judge checking if the generated answer is supported by the retrieved context, with `unsupported_claims` field.

**Rationale:**
- Simple RAG pipelines can hallucinate when the LLM fills gaps with training knowledge rather than context.
- Score < 0.6 triggers a user warning rather than blocking (to preserve usability for partially grounded answers).
- The `unsupported_claims` field in the JSON response makes hallucinated content explicit in the trace.

**Fail-Fast alignment:** Hallucinated answers are flagged with a visible warning before reaching the user. The trace records the specific unsupported claims.

---

### 6. Guardrail: Hardware Scope Enforcement

**Choice:** LLM-based guardrail checking if the answer discusses devices not in the retrieved context.

**Problem it solves:** A query about "Nokia 7750 BGP" might retrieve a Cisco ASR 9000 document by similarity. The generator might then give Cisco-specific CLI commands in response to a Nokia question — correct syntax, wrong device.

**How it works:**
1. Collect `mentioned_devices` from retrieved doc metadata.
2. Pass allowed devices + generated answer to the guardrail LLM.
3. If the answer gives specific instructions for out-of-scope hardware → FAIL → blocked with explanation.

**Fail-open design:** On guardrail LLM error, the answer passes through with a log warning (prioritizes availability over perfectionism for guardrail errors only).

---

### 7. ChromaDB + HuggingFace Embeddings (Open Source)

**Choice:** `all-MiniLM-L6-v2` embeddings (384-dim) locally, ChromaDB for persistence.

**Rationale:**
- Zero API cost — embeddings run fully locally via `sentence-transformers`.
- `all-MiniLM-L6-v2` achieves 80%+ of OpenAI `text-embedding-3-small` quality on semantic search benchmarks.
- ChromaDB persists to disk between restarts, avoiding re-ingestion on every boot.
- Document metadata (device, category) enables post-retrieval filtering if needed.

---

### 8. Structured Logging (structlog)

**Choice:** structlog with ISO timestamps, key-value context, and file output.

**Every decision node logs:**
```json
{
  "timestamp": "2024-01-15T10:23:41.123Z",
  "level": "info",
  "event": "RAG decision",
  "node": "grade_relevance",
  "decision": "relevant",
  "relevance_score": 0.87,
  "query": "How to reset Cisco ASR..."
}
```

This enables:
- Grep-based debugging: `grep "grade_relevance" logs/app.log | jq '.relevance_score'`
- Alerting on low relevance scores across sessions
- Audit trail for compliance

---

## Failure Mode Analysis

| Failure | Detection | Response |
|---|---|---|
| Vector DB empty | `retrieve_node` returns `[]` | Log warning; route to "no context" answer |
| LLM API timeout | `try/except` in each node | Return error state; pipeline continues |
| JSON parse failure | `_parse_json_response()` fallback | Regex extraction; default to safe values |
| Infinite rewrite loop | `MAX_REWRITE_ATTEMPTS` guard | Force generate after N attempts |
| Hallucination | Groundedness score < 0.6 | Flag answer with warning prefix |
| Out-of-scope device | Guardrail FAIL | Block answer, return explanation |
| Startup failure | Lifespan exception handling | Log error; health endpoint reports degraded |

---

## Performance Characteristics

| Metric | Typical Value | Notes |
|---|---|---|
| Retrieval latency | ~50ms | ChromaDB local similarity search |
| LLM calls per query | 3–4 | Relevance + Generate + Groundedness + Guardrail |
| Total pipeline time | 3–8 seconds | Depends on LLM provider |
| Rewrite overhead | +2–4 seconds | Only on cache miss / irrelevant context |
| Embedding model load | ~2s (once) | Cached after first request |

---

## What "Fail-Fast" Means in This System

1. **Retrieval fail-fast**: If ChromaDB returns nothing, we don't call the LLM — we return a "no context" message immediately.
2. **Relevance gate**: The LLM generator is only called after the grader confirms context quality. Irrelevant context → rewrite, not generate.
3. **Groundedness gate**: Users don't receive potentially hallucinated answers without an explicit warning flag.
4. **Guardrail gate**: Hardware-scope violations are caught before the answer reaches the user.
5. **Exception isolation**: Each node's failure is caught, logged, and converted to a safe fallback — no unhandled exceptions crash the pipeline.
6. **Max retry cap**: Prevents runaway API costs from infinite rewrite loops.

The system prioritizes **transparency over silence** — every decision, score, and failure is recorded in the decision trace visible in both the UI and LangSmith.
