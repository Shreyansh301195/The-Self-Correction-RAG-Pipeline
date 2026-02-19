# 📋 Evaluation Log — Fail-Fast Design Summary

> **Project:** Corrective RAG — Telecom OSS/BSS Support System
> **Scenario:** Self-Correction RAG Pipeline
> **Domain:** Telecom Customer Support (OSS/BSS)

---

## Core Principle

> **"Fail early, fail loudly, fail safely"** — every failure point in the pipeline is caught, logged, and converted into a safe fallback before reaching the user.

The system is built around a **LangGraph state machine** where each node acts as a quality gate. The pipeline spends compute only when the previous gate confirms quality — expensive operations (LLM generation) are always gated behind cheap checks (relevance scoring).

---

## 6 Explicit Fail-Fast Gates

| # | Gate | Location | Trigger | Action |
|---|---|---|---|---|
| 1 | **Empty Retrieval** | `retrieve_node` | ChromaDB returns 0 docs | Return "no context" immediately — skip LLM entirely |
| 2 | **Relevance Gate** | `grade_relevance_node` | Score < 0.5 | Block generation — rewrite query instead |
| 3 | **Max Retry Cap** | `route_after_grading` | Rewrites ≥ 2 | Force-exit loop — generate with partial context |
| 4 | **Groundedness Gate** | `check_groundedness_node` | Score < 0.6 | Flag hallucination warning before answer reaches user |
| 5 | **Guardrail Block** | `guardrail_node` | Out-of-scope hardware detected | Block answer entirely — return explanation to user |
| 6 | **Exception Isolation** | Every node | Any API / runtime error | Caught locally, logged with context, safe default returned |

---

## Design Decisions That Enforce Fail-Fast

### 1. Relevance Check BEFORE Generation
The most expensive operation (LLM generation) only runs after the relevance grader confirms the context is useful. Bad context triggers a rewrite — never wasting tokens generating a wrong answer.

```
retrieve → grade (cheap LLM call)
               │
               ├── FAIL (score < 0.5) → rewrite query → retrieve again
               │
               └── PASS (score ≥ 0.5) → generate (expensive LLM call)
```

---

### 2. LLM-as-Judge Returns Structured JSON with Scores
Every evaluator returns a **numeric score + reasoning**, not just yes/no. Failures are measurable — thresholds are tunable via environment variables rather than hardcoded binary decisions.

```json
{
  "score": 0.31,
  "decision": "irrelevant",
  "reasoning": "Context discusses Nokia CLI, query asks about Cisco reset procedure"
}
```

Configurable thresholds in `.env`:
```env
RELEVANCE_THRESHOLD=0.5
MAX_REWRITE_ATTEMPTS=2
```

---

### 3. Every Node is Fully Isolated with try/except
No single node failure can crash the pipeline. Every exception is caught, logged with full context, and converted to a safe state:

```python
except Exception as e:
    logger.error("Relevance grading failed", error=str(e))
    # Default to 0.0 = irrelevant = triggers rewrite (safe)
    return {**state, "relevance_score": 0.0}
```

---

### 4. Deliberate Fail-Safe vs Fail-Open Decisions

| Component | Default on Error | Reasoning |
|---|---|---|
| Relevance grader | `0.0` (fail-safe) | Correctness prioritized — bad context triggers rewrite |
| Groundedness checker | `0.5` (neutral) | Balanced — don't block valid answers on evaluator errors |
| Guardrail | `True` (fail-open) | Availability prioritized — guardrail errors shouldn't block users |

---

### 5. Max Retry Cap Prevents Runaway Costs
Without a cap, an irrelevant query could loop forever burning API tokens. `MAX_REWRITE_ATTEMPTS=2` is a hard ceiling — after 2 failed rewrites the pipeline forces generation with whatever context it has, rather than looping infinitely.

```python
elif rewrite_count >= settings.MAX_REWRITE_ATTEMPTS:
    logger.warning("Max retries reached → GENERATE with partial context")
    return "generate"   # force exit from loop
```

---

### 6. Full Decision Trace on Every Run — No Silent Failures
Every gate decision is recorded in the `decision_log` array, visible in both the React UI and LangSmith. A typical successful run looks like:

```
retrieve      → retrieved       docs_count=4, top_device=Cisco ASR 9000
grade         → irrelevant      score=0.31, threshold=0.5       ← FAIL-FAST triggered
rewrite       → rewritten       attempt=1
retrieve      → retrieved       docs_count=4, top_device=Cisco ASR 9000
grade         → relevant        score=0.87                       ← PASS
generate      → generated       answer_length=412, sources=4
groundedness  → grounded        score=0.91
guardrail     → guardrail_pass  passed=True
finalize      → completed
```

A blocked run looks like:
```
retrieve      → retrieved       docs_count=4
grade         → relevant        score=0.79
generate      → generated       answer_length=380
groundedness  → hallucinated    score=0.41, unsupported_claims=[...]  ← FAIL-FAST
finalize      → completed       (with hallucination warning prefix)
```

---

## Pipeline Flow Summary

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  GATE 1: Empty Retrieval Check                          │
│  0 docs → immediate "no context" response               │
└──────────────────────────┬──────────────────────────────┘
                           │ docs found
                           ▼
┌─────────────────────────────────────────────────────────┐
│  GATE 2: Relevance Scoring (LLM-as-judge, score 0-1)    │
│  < 0.5 → rewrite query and retry                        │
│  ≥ 2 rewrites → GATE 3                                  │
└──────────────────────────┬──────────────────────────────┘
                           │ relevant
                           ▼
┌─────────────────────────────────────────────────────────┐
│  GATE 3: Max Retry Cap                                  │
│  rewrites ≥ 2 → force generate (exit loop)              │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
                      LLM Generation
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  GATE 4: Groundedness Check (LLM-as-judge, score 0-1)   │
│  < 0.6 → add hallucination warning to answer            │
└──────────────────────────┬──────────────────────────────┘
                           │ grounded
                           ▼
┌─────────────────────────────────────────────────────────┐
│  GATE 5: Guardrail (LLM-as-judge)                       │
│  out-of-scope hardware → block answer entirely          │
└──────────────────────────┬──────────────────────────────┘
                           │ passed
                           ▼
                     Final Answer
```

---

## Observability as a Fail-Fast Enabler

Fail-fast only works if failures are **visible**. This system provides three observability layers:

| Layer | Tool | What It Shows |
|---|---|---|
| **Distributed Tracing** | LangSmith | Full call graph, LLM inputs/outputs, token usage, latency per node |
| **Structured Logging** | structlog (JSON) | Every decision with scores, thresholds, and reasoning |
| **UI Trace Viewer** | React frontend | Decision log timeline with expand/collapse per step |

Every failure produces a structured log entry:
```json
{
  "timestamp": "2026-02-20T00:10:14Z",
  "level": "warning",
  "event": "RAG decision",
  "node": "grade_relevance",
  "decision": "irrelevant",
  "relevance_score": 0.31,
  "threshold": 0.5,
  "reasoning": "Context discusses Nokia CLI, query asks about Cisco"
}
```

---

## Summary

| Principle | How It's Implemented |
|---|---|
| **Fail early** | Relevance gate runs before generation — cheap check blocks expensive call |
| **Fail loudly** | Every decision logged to structlog + LangSmith — nothing fails silently |
| **Fail safely** | Every node has try/except with safe defaults — no unhandled exceptions |
| **Fail cheaply** | Irrelevant queries are caught at grade step — LLM generator never called |
| **Fail visibly** | Full decision trace in UI + LangSmith — every gate decision is auditable |

> The system is designed so that **the cheapest check always runs first**, **every failure produces a safe default**, and **nothing fails silently**. This is the Fail-Fast mindset applied to a production LLM pipeline.