# 🌐 Corrective RAG — Telecom OSS/BSS Support System

A production-grade **Self-Correcting RAG pipeline** for Telecom technical support, built with **LangGraph**, **LangSmith**, **FastAPI**, and **React**.

---

## 📐 Architecture

```
User Query
    │
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        LangGraph State Machine                       │
│                                                                      │
│  ┌─────────┐    ┌──────────────┐    ┌───────────────┐              │
│  │ Retrieve │───▶│ Grade        │───▶│ Generate      │              │
│  │ (ChromaDB│    │ Relevance    │    │ (LLM)         │              │
│  │ + HF    │    │ (LLM-judge)  │    └───────┬───────┘              │
│  │ Embeddings)   └──────┬───────┘            │                      │
│  └─────────┘           │ irrelevant          ▼                      │
│       ▲                ▼            ┌──────────────────┐            │
│       │         ┌──────────────┐   │ Check            │            │
│       └─────────│ Rewrite      │   │ Groundedness     │            │
│  (retry loop)   │ Query (LLM)  │   │ (LLM-judge)      │            │
│                 └──────────────┘   └────────┬─────────┘            │
│                                             │ grounded              │
│                                             ▼                       │
│                                    ┌──────────────────┐             │
│                                    │ Guardrail Check  │             │
│                                    │ (LLM-judge)      │             │
│                                    └────────┬─────────┘             │
│                                             │ pass/fail             │
│                                             ▼                       │
│                                    ┌──────────────────┐             │
│                                    │ Finalize Answer  │             │
│                                    └──────────────────┘             │
└──────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
    LangSmith            ChromaDB            Structured Logs
    (Traces)            (Vector DB)          (structlog JSON)
```

### Component Responsibilities

| Component | Role |
|---|---|
| **ChromaDB** | Local vector store with `all-MiniLM-L6-v2` embeddings |
| **Relevance Grader** | LLM-as-judge: scores retrieved context 0–1 against query |
| **Query Rewriter** | Reformulates failed queries for better recall |
| **Generator** | Produces answers strictly from retrieved context |
| **Groundedness Checker** | Verifies no hallucinated claims in the answer |
| **Guardrail** | Blocks answers referencing hardware not in context |
| **LangSmith** | Full distributed tracing of every LLM call |
| **FastAPI** | REST API with session-based trace storage |
| **React + Vite** | Dark-themed UI with real-time trace visualization |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- API key for OpenAI, OpenRouter (open-source models), or local Ollama

### 1. Clone & Set Up Backend

```bash
cd corrective-rag/backend
cp .env.example .env
# Edit .env with your API keys
pip install -r requirements.txt
```

### 2. Configure LLM (choose one)

**Option A — OpenAI (gpt-4o-mini):**
```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

**Option B — Open-source via OpenRouter (Mistral, LLaMA3):**
```env
OPENAI_API_KEY=sk-or-...         # OpenRouter key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=mistralai/mistral-7b-instruct
```

**Option C — Local Ollama (fully offline):**
```bash
# Install Ollama: https://ollama.ai
ollama pull llama3
```
```env
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3
```

### 3. Configure LangSmith (optional but recommended)

```env
LANGCHAIN_API_KEY=ls__...        # Get from https://smith.langchain.com
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=corrective-rag-telecom
```

### 4. Start Backend

```bash
cd backend
python main.py
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 5. Set Up & Start Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
# UI available at http://localhost:3000
```

---

## 📡 API Reference

### `POST /query`
Run the full Corrective RAG pipeline.

```json
{
  "query": "How do I reset a Cisco ASR 9000 router to factory defaults?"
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "query": "...",
  "final_answer": "...",
  "scores": {
    "relevance": 0.87,
    "groundedness": 0.91,
    "guardrail_passed": true
  },
  "metadata": {
    "rewrite_count": 0,
    "rewritten_query": "",
    "sources_used": [...],
    "mentioned_devices": ["Cisco ASR 9000"]
  },
  "decision_trace": [
    {"node": "retrieve", "decision": "retrieved", "details": {...}},
    {"node": "grade_relevance", "decision": "relevant", "details": {"relevance_score": 0.87}},
    {"node": "generate", "decision": "generated", "details": {...}},
    {"node": "check_groundedness", "decision": "grounded", "details": {"groundedness_score": 0.91}},
    {"node": "guardrail", "decision": "guardrail_pass", "details": {...}},
    {"node": "finalize", "decision": "completed", "details": {...}}
  ],
  "processing_time_ms": 3241.5
}
```

### Other Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /health` | GET | System health check |
| `GET /sample-queries` | GET | Pre-built test queries |
| `GET /trace/{session_id}` | GET | Retrieve session trace |
| `GET /sessions` | GET | List recent sessions |
| `POST /ingest` | POST | Re-ingest documents |

---

## 🔄 Pipeline Decision Logic

```
retrieve → grade_relevance
    ├── score ≥ 0.5 → generate
    └── score < 0.5
        ├── rewrites < 2 → rewrite_query → retrieve (loop)
        └── rewrites ≥ 2 → generate (with partial/no context)

generate → check_groundedness
    ├── score ≥ 0.6 → guardrail
    └── score < 0.6 → finalize (with hallucination warning)

guardrail
    ├── passed → finalize (normal answer)
    └── failed → finalize (blocked with explanation)
```

### Fail-Fast Design Principles

1. **Empty Retrieval**: Returns immediately with "no context" message rather than hallucinating
2. **Relevance Threshold**: 0.5 score triggers rewrite before wasting LLM tokens on bad context
3. **Max Retry Guard**: Hard cap of 2 rewrites prevents infinite loops
4. **Groundedness Gate**: Answers scoring < 0.6 are flagged before reaching users
5. **Guardrail Block**: Out-of-scope device instructions are intercepted regardless of quality scores
6. **Error Isolation**: Each node catches its own exceptions; failures propagate gracefully

---

## 📊 LangSmith Observability

When `LANGCHAIN_API_KEY` is set, every pipeline run creates a **LangSmith trace** with:

- Full call graph showing each node execution
- LLM input/output for every judge call (relevance, groundedness, guardrail)
- Token usage and latency per node
- Custom metadata: relevance scores, rewrite counts, device context

View traces at: [https://smith.langchain.com](https://smith.langchain.com) → Project: `corrective-rag-telecom`

### Local Structured Logs

Without LangSmith, every decision is logged as structured JSON:
```
[INFO] RAG decision node=retrieve decision=retrieved query="How to reset Cisco..." docs_count=4
[INFO] RAG decision node=grade_relevance decision=relevant relevance_score=0.87 threshold=0.5
[INFO] RAG decision node=generate decision=generated answer_length=412 sources_used=4
[INFO] RAG decision node=check_groundedness decision=grounded groundedness_score=0.91
[INFO] RAG decision node=guardrail decision=guardrail_pass passed=True
[INFO] RAG decision node=finalize decision=completed guardrail_passed=True
```

---

## 🧪 Test Scenarios

| Query | Expected Path | Tests |
|---|---|---|
| "How to reset Cisco ASR 9000?" | retrieve → relevant → generate → grounded → pass | Happy path |
| "MPLS config on Nokia 7750" | retrieve → relevant → generate → grounded → pass | Device-specific retrieval |
| "pizza recipe" | retrieve → irrelevant → rewrite × 2 → generate (no context) | Irrelevance + retry loop |
| "BGP on Juniper MX" | retrieve → relevant → generate → guardrail check | Out-of-scope guardrail test |

---

## 🗂️ Project Structure

```
corrective-rag/
├── backend/
│   ├── main.py           # FastAPI app with lifespan startup
│   ├── rag_graph.py      # LangGraph state machine (core logic)
│   ├── vector_store.py   # ChromaDB ingestion & retrieval
│   ├── llm_client.py     # OpenAI-compatible LLM wrapper
│   ├── config.py         # Settings from .env
│   ├── logger.py         # structlog configuration
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx                      # Root component + layout
│   │   ├── App.css                      # Dark theme styles
│   │   ├── components/
│   │   │   ├── QueryInterface.jsx       # Query form + answer display
│   │   │   ├── TraceViewer.jsx          # Decision trace visualization
│   │   │   ├── ScoreCard.jsx            # Evaluation scores display
│   │   │   ├── SampleQueries.jsx        # Pre-built test queries
│   │   │   └── ArchitectureDiagram.jsx  # SVG architecture diagram
│   │   └── hooks/
│   │       └── useRAGQuery.js           # API integration hook
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
├── data/
│   └── telecom_manuals.json    # Sample telecom docs (10 entries)
├── logs/
│   └── app.log
└── README.md
```

---

## 🏗️ Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Agent Framework** | LangGraph | State machine with conditional edges, perfect for iterative RAG |
| **LLM** | Any OpenAI-compatible (Mistral, LLaMA3, GPT-4o-mini) | Flexible, supports fully open-source local inference |
| **Embeddings** | `all-MiniLM-L6-v2` (HuggingFace) | Free, fast, no API key, runs locally |
| **Vector DB** | ChromaDB | Local, zero-config, great for prototyping |
| **Observability** | LangSmith + structlog | Full distributed traces + structured JSON logs |
| **API** | FastAPI | Async, auto-docs, Pydantic validation |
| **Frontend** | React + Vite | Fast HMR, modern, component-based |

---

## 📋 Evaluation Log

See `EVALUATION_LOG.md` for the full design rationale and failure analysis.
