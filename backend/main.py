"""
FastAPI Backend for Corrective RAG Telecom Support System.
Endpoints: /query, /ingest, /health, /trace/{session_id}
"""
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import settings
from logger import get_logger, setup_logging
from rag_graph import run_rag_pipeline, get_compiled_graph
from vector_store import initialize_vector_store

# Set up logging before anything else
setup_logging()

# Configure LangSmith env vars
if settings.LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGCHAIN_TRACING_V2
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT

logger = get_logger("api")

# In-memory session store (use Redis in production)
session_store: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    logger.info("Starting Corrective RAG API server")
    try:
        # Initialize vector store
        data_path = os.path.join(os.path.dirname(__file__), "../data/telecom_manuals.json")
        initialize_vector_store(data_path)
        logger.info("Vector store ready")

        # Pre-warm the graph
        get_compiled_graph()
        logger.info("LangGraph compiled and ready")

    except Exception as e:
        logger.error("Startup failed", error=str(e))
        # Don't crash — let health endpoint report degraded status

    yield

    logger.info("Shutting down API server")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Corrective RAG - Telecom OSS/BSS Support",
    description="Self-correcting RAG pipeline with LangGraph, relevance grading, and guardrails",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="User question")
    session_id: Optional[str] = Field(None, description="Optional session ID for tracing")


class ScoresResponse(BaseModel):
    relevance: float
    groundedness: float
    guardrail_passed: bool


class SourceInfo(BaseModel):
    device: Optional[str]
    category: Optional[str]
    snippet: str


class MetadataResponse(BaseModel):
    rewrite_count: int
    rewritten_query: str
    sources_used: list[SourceInfo]
    mentioned_devices: list[str]
    error: Optional[str]


class QueryResponse(BaseModel):
    session_id: str
    query: str
    final_answer: str
    scores: ScoresResponse
    metadata: MetadataResponse
    decision_trace: list[dict]
    processing_time_ms: float


class IngestRequest(BaseModel):
    data_path: Optional[str] = Field(None, description="Path to JSON data file")


class IngestResponse(BaseModel):
    status: str
    chunks_ingested: int
    message: str


class HealthResponse(BaseModel):
    status: str
    vector_store: str
    llm_model: str
    langsmith_enabled: bool
    version: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    from vector_store import get_vector_store
    vs = get_vector_store()

    vs_status = "healthy" if vs.vectorstore is not None else "not_initialized"

    return HealthResponse(
        status="healthy",
        vector_store=vs_status,
        llm_model=settings.LLM_MODEL,
        langsmith_enabled=bool(settings.LANGCHAIN_API_KEY),
        version="1.0.0"
    )


@app.post("/query", response_model=QueryResponse, tags=["RAG"])
async def query_endpoint(request: QueryRequest):
    """
    Main RAG query endpoint.
    Runs the full Corrective RAG pipeline: retrieve → grade → rewrite → generate → guardrail.
    """
    session_id = request.session_id or str(uuid.uuid4())
    logger.info("Query received", session_id=session_id, query=request.query[:80])

    start_time = time.time()

    try:
        result = await run_rag_pipeline(request.query)
    except Exception as e:
        logger.error("Query endpoint error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")

    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    # Store in session cache
    session_store[session_id] = {**result, "session_id": session_id, "processing_time_ms": elapsed_ms}

    response = QueryResponse(
        session_id=session_id,
        query=result["query"],
        final_answer=result["final_answer"],
        scores=ScoresResponse(**result["scores"]),
        metadata=MetadataResponse(
            rewrite_count=result["metadata"]["rewrite_count"],
            rewritten_query=result["metadata"].get("rewritten_query", ""),
            sources_used=[SourceInfo(**s) for s in result["metadata"]["sources_used"]],
            mentioned_devices=result["metadata"]["mentioned_devices"],
            error=result["metadata"].get("error")
        ),
        decision_trace=result["decision_trace"],
        processing_time_ms=elapsed_ms
    )

    logger.info(
        "Query completed",
        session_id=session_id,
        elapsed_ms=elapsed_ms,
        relevance=result["scores"]["relevance"],
        groundedness=result["scores"]["groundedness"]
    )

    return response


@app.get("/trace/{session_id}", tags=["Observability"])
async def get_trace(session_id: str):
    """Retrieve the decision trace for a specific session."""
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session_store[session_id]


@app.get("/sessions", tags=["Observability"])
async def list_sessions():
    """List all session IDs stored in memory."""
    return {
        "count": len(session_store),
        "sessions": [
            {
                "session_id": sid,
                "query": data.get("query", "")[:60],
                "scores": data.get("scores", {})
            }
            for sid, data in list(session_store.items())[-20:]  # Last 20
        ]
    }


@app.post("/ingest", response_model=IngestResponse, tags=["Admin"])
async def ingest_documents(request: IngestRequest = IngestRequest()):
    """Re-ingest documents into the vector store."""
    data_path = request.data_path or os.path.join(
        os.path.dirname(__file__), "../data/telecom_manuals.json"
    )

    if not os.path.exists(data_path):
        raise HTTPException(status_code=404, detail=f"Data file not found: {data_path}")

    try:
        vs = initialize_vector_store(data_path)
        chunks = vs.vectorstore._collection.count() if vs.vectorstore else 0
        return IngestResponse(
            status="success",
            chunks_ingested=chunks,
            message=f"Successfully ingested documents from {data_path}"
        )
    except Exception as e:
        logger.error("Ingestion failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.get("/sample-queries", tags=["Demo"])
async def sample_queries():
    """Return sample queries for testing different RAG paths."""
    return {
        "queries": [
            {
                "id": 1,
                "query": "How do I reset a Cisco ASR 9000 router to factory defaults?",
                "expected_path": "relevant → generate → grounded → pass",
                "device": "Cisco ASR 9000"
            },
            {
                "id": 2,
                "query": "What are the BGP troubleshooting steps for Nokia 7750?",
                "expected_path": "relevant → generate → grounded → pass",
                "device": "Nokia 7750 SR"
            },
            {
                "id": 3,
                "query": "How to configure QoS on Juniper MX routers?",
                "expected_path": "may rewrite → retrieve → generate",
                "device": "Juniper MX Series"
            },
            {
                "id": 4,
                "query": "pizza recipe",
                "expected_path": "irrelevant → rewrite → max_retries → generate (no context)",
                "device": "N/A (tests irrelevance path)"
            },
            {
                "id": 5,
                "query": "MPLS label configuration on Nokia SR",
                "expected_path": "relevant → generate → grounded → pass",
                "device": "Nokia 7750 SR"
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level="info"
    )
