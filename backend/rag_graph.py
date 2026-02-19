"""
Corrective RAG Pipeline implemented as a LangGraph state machine.

Flow:
  User Query
    → Retrieve Documents
    → Grade Relevance (LLM-as-judge)
    → [RELEVANT] Generate Answer → Groundedness Check → [GROUNDED] Guardrail → Final Answer
    → [IRRELEVANT] Rewrite Query → Retrieve Again (max N attempts)
    → [HALLUCINATED] Reject / Regenerate
    → [GUARDRAIL_FAIL] Block out-of-scope answer

Each step is logged with structured traces for full observability.
"""
from __future__ import annotations

import json
import re
import time
from typing import TypedDict, List, Annotated, Optional
from enum import Enum

from langchain.schema import Document, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from config import settings
from llm_client import get_llm_client
from vector_store import get_vector_store
from logger import get_logger

logger = get_logger("rag_graph")


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class RAGState(TypedDict):
    """Complete mutable state passed through the LangGraph nodes."""
    query: str                        # Original user query
    rewritten_query: str              # Possibly rewritten query
    retrieved_docs: List[Document]    # Raw retrieved docs
    relevant_docs: List[Document]     # Filtered relevant docs
    generation: str                   # LLM generated answer
    relevance_score: float            # 0.0–1.0
    groundedness_score: float         # 0.0–1.0
    guardrail_passed: bool            # Guardrail check result
    rewrite_count: int                # Number of rewrites attempted
    decision_log: List[dict]          # Trace of decisions made
    final_answer: str                 # Final output to user
    error: Optional[str]              # Error message if any
    mentioned_devices: List[str]      # Devices mentioned in query context


class Decision(str, Enum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    GROUNDED = "grounded"
    HALLUCINATED = "hallucinated"
    GUARDRAIL_PASS = "guardrail_pass"
    GUARDRAIL_FAIL = "guardrail_fail"
    MAX_RETRIES = "max_retries"


# ---------------------------------------------------------------------------
# Helper: append to decision log
# ---------------------------------------------------------------------------

def log_decision(state: RAGState, node: str, decision: str, details: dict = None) -> dict:
    entry = {
        "timestamp": time.time(),
        "node": node,
        "decision": decision,
        "details": details or {}
    }
    logger.info(
        "RAG decision",
        node=node,
        decision=decision,
        query=state["query"][:60],
        **{k: v for k, v in (details or {}).items() if isinstance(v, (str, int, float, bool))}
    )
    return entry


# ---------------------------------------------------------------------------
# Node 1: Retrieve
# ---------------------------------------------------------------------------

def retrieve_node(state: RAGState) -> RAGState:
    """Retrieve documents from vector store using current query."""
    query = state.get("rewritten_query") or state["query"]
    logger.info("RETRIEVE node", query=query[:80], attempt=state.get("rewrite_count", 0))

    try:
        vs = get_vector_store()
        docs = vs.retrieve(query)

        if not docs:
            logger.warning("No documents retrieved", query=query[:80])

        entry = log_decision(state, "retrieve", "retrieved", {
            "query_used": query[:80],
            "docs_count": len(docs),
            "devices_found": list({d.metadata.get("device", "unknown") for d in docs})
        })

        return {
            **state,
            "retrieved_docs": docs,
            "decision_log": state.get("decision_log", []) + [entry]
        }
    except Exception as e:
        logger.error("Retrieve node failed", error=str(e))
        return {
            **state,
            "retrieved_docs": [],
            "error": f"Retrieval error: {e}",
            "decision_log": state.get("decision_log", []) + [
                log_decision(state, "retrieve", "error", {"error": str(e)})
            ]
        }


# ---------------------------------------------------------------------------
# Node 2: Grade Relevance
# ---------------------------------------------------------------------------

RELEVANCE_SYSTEM = """You are an expert relevance grader for a Telecom OSS/BSS support system.
Given a user question and retrieved context, determine if the context is relevant.

Respond in JSON with exactly:
{
  "score": <float 0.0-1.0>,
  "decision": "relevant" | "irrelevant",
  "reasoning": "<one sentence>"
}

Score guidelines:
- 0.8-1.0: Context directly answers the question
- 0.5-0.7: Context partially relevant, some useful info
- 0.0-0.4: Context is unrelated or misleading

A score >= 0.5 is considered relevant."""


def grade_relevance_node(state: RAGState) -> RAGState:
    """LLM-as-judge: evaluate if retrieved context is relevant to the query."""
    logger.info("GRADE_RELEVANCE node", query=state["query"][:80])

    docs = state.get("retrieved_docs", [])
    if not docs:
        entry = log_decision(state, "grade_relevance", Decision.IRRELEVANT, {
            "reason": "No documents retrieved",
            "relevance_score": 0.0
        })
        return {
            **state,
            "relevance_score": 0.0,
            "relevant_docs": [],
            "decision_log": state.get("decision_log", []) + [entry]
        }

    # Build context from top docs
    context = "\n\n---\n\n".join([
        f"[Device: {d.metadata.get('device', 'Unknown')}]\n{d.page_content}"
        for d in docs[:3]
    ])

    try:
        llm = get_llm_client()
        response = llm.chat(
            system=RELEVANCE_SYSTEM,
            user=f"Question: {state['query']}\n\nContext:\n{context}",
            run_name="relevance_grader"
        )

        # Parse JSON response
        parsed = _parse_json_response(response)
        score = float(parsed.get("score", 0.0))
        decision = Decision.RELEVANT if score >= settings.RELEVANCE_THRESHOLD else Decision.IRRELEVANT
        reasoning = parsed.get("reasoning", "No reasoning provided")

        entry = log_decision(state, "grade_relevance", decision, {
            "relevance_score": score,
            "threshold": settings.RELEVANCE_THRESHOLD,
            "reasoning": reasoning
        })

        return {
            **state,
            "relevance_score": score,
            "relevant_docs": docs if decision == Decision.RELEVANT else [],
            "decision_log": state.get("decision_log", []) + [entry]
        }

    except Exception as e:
        logger.error("Relevance grading failed", error=str(e))
        # Fail-safe: treat as irrelevant to force rewrite
        entry = log_decision(state, "grade_relevance", "error", {"error": str(e)})
        return {
            **state,
            "relevance_score": 0.0,
            "relevant_docs": [],
            "error": f"Relevance grading error: {e}",
            "decision_log": state.get("decision_log", []) + [entry]
        }


# ---------------------------------------------------------------------------
# Node 3: Rewrite Query
# ---------------------------------------------------------------------------

REWRITE_SYSTEM = """You are an expert query rewriter for a Telecom OSS/BSS knowledge base.
The original query did not retrieve relevant context. Rewrite the query to be more specific and technical.
Focus on: device names, error codes, protocols (BGP, MPLS, OSPF), or specific operations.
Return ONLY the rewritten query, nothing else."""


def rewrite_query_node(state: RAGState) -> RAGState:
    """Rewrite the query to improve retrieval quality."""
    logger.info("REWRITE_QUERY node", attempt=state.get("rewrite_count", 0) + 1)

    try:
        llm = get_llm_client()
        rewritten = llm.chat(
            system=REWRITE_SYSTEM,
            user=f"Original query: {state['query']}\n\nRewrite to improve technical document retrieval:",
            run_name="query_rewriter"
        )

        new_count = state.get("rewrite_count", 0) + 1
        entry = log_decision(state, "rewrite_query", "rewritten", {
            "original": state["query"][:80],
            "rewritten": rewritten[:80],
            "attempt": new_count
        })

        return {
            **state,
            "rewritten_query": rewritten,
            "rewrite_count": new_count,
            "decision_log": state.get("decision_log", []) + [entry]
        }

    except Exception as e:
        logger.error("Query rewriting failed", error=str(e))
        entry = log_decision(state, "rewrite_query", "error", {"error": str(e)})
        return {
            **state,
            "rewrite_count": state.get("rewrite_count", 0) + 1,
            "error": f"Rewrite error: {e}",
            "decision_log": state.get("decision_log", []) + [entry]
        }


# ---------------------------------------------------------------------------
# Node 4: Generate Answer
# ---------------------------------------------------------------------------

GENERATE_SYSTEM = """You are an expert Telecom OSS/BSS support engineer.
Answer the user's question using ONLY the provided context documents.
Be precise and technical. If the context does not contain enough information, say so explicitly.
Do NOT invent commands, IP addresses, or procedures not mentioned in the context.
Structure your answer clearly with steps if applicable."""


def generate_node(state: RAGState) -> RAGState:
    """Generate an answer from the relevant documents."""
    logger.info("GENERATE node")

    docs = state.get("relevant_docs") or state.get("retrieved_docs", [])
    if not docs:
        no_context_answer = (
            "I was unable to find relevant documentation for your query. "
            "Please check device model names or rephrase your question."
        )
        entry = log_decision(state, "generate", "no_context", {})
        return {
            **state,
            "generation": no_context_answer,
            "decision_log": state.get("decision_log", []) + [entry]
        }

    context = "\n\n---\n\n".join([
        f"[Source: {d.metadata.get('device', 'Unknown')} - {d.metadata.get('category', '')}]\n{d.page_content}"
        for d in docs[:4]
    ])

    # Extract device names mentioned in context (for guardrail)
    mentioned_devices = list({
        d.metadata.get("device", "unknown")
        for d in docs
        if d.metadata.get("device")
    })

    try:
        llm = get_llm_client()
        answer = llm.chat(
            system=GENERATE_SYSTEM,
            user=f"Context:\n{context}\n\nQuestion: {state['query']}",
            run_name="answer_generator"
        )

        entry = log_decision(state, "generate", "generated", {
            "answer_length": len(answer),
            "sources_used": len(docs),
            "devices": mentioned_devices
        })

        return {
            **state,
            "generation": answer,
            "mentioned_devices": mentioned_devices,
            "decision_log": state.get("decision_log", []) + [entry]
        }

    except Exception as e:
        logger.error("Generation failed", error=str(e))
        entry = log_decision(state, "generate", "error", {"error": str(e)})
        return {
            **state,
            "generation": "Generation failed due to an internal error.",
            "error": f"Generation error: {e}",
            "decision_log": state.get("decision_log", []) + [entry]
        }


# ---------------------------------------------------------------------------
# Node 5: Check Groundedness
# ---------------------------------------------------------------------------

GROUNDEDNESS_SYSTEM = """You are a groundedness evaluator for a RAG system.
Check if the generated answer is fully supported by the provided context.

Respond in JSON:
{
  "score": <float 0.0-1.0>,
  "decision": "grounded" | "hallucinated",
  "reasoning": "<one sentence>",
  "unsupported_claims": ["<claim1>", ...]
}

Score guidelines:
- 0.8-1.0: All claims directly supported by context
- 0.5-0.7: Mostly supported, minor extrapolation
- 0.0-0.4: Contains significant unsupported or fabricated claims
Score >= 0.6 = grounded."""


def check_groundedness_node(state: RAGState) -> RAGState:
    """Evaluate if the generated answer is grounded in the retrieved context."""
    logger.info("CHECK_GROUNDEDNESS node")

    docs = state.get("relevant_docs") or state.get("retrieved_docs", [])
    context = "\n\n".join([d.page_content for d in docs[:4]])

    try:
        llm = get_llm_client()
        response = llm.chat(
            system=GROUNDEDNESS_SYSTEM,
            user=f"Context:\n{context}\n\nGenerated Answer:\n{state['generation']}",
            run_name="groundedness_checker"
        )

        parsed = _parse_json_response(response)
        score = float(parsed.get("score", 0.0))
        decision = Decision.GROUNDED if score >= 0.6 else Decision.HALLUCINATED
        reasoning = parsed.get("reasoning", "")
        unsupported = parsed.get("unsupported_claims", [])

        entry = log_decision(state, "check_groundedness", decision, {
            "groundedness_score": score,
            "reasoning": reasoning,
            "unsupported_claims": unsupported
        })

        return {
            **state,
            "groundedness_score": score,
            "decision_log": state.get("decision_log", []) + [entry]
        }

    except Exception as e:
        logger.error("Groundedness check failed", error=str(e))
        entry = log_decision(state, "check_groundedness", "error", {"error": str(e)})
        return {
            **state,
            "groundedness_score": 0.5,  # neutral on error
            "error": f"Groundedness error: {e}",
            "decision_log": state.get("decision_log", []) + [entry]
        }


# ---------------------------------------------------------------------------
# Node 6: Guardrail Check
# ---------------------------------------------------------------------------
GUARDRAIL_SYSTEM = """You are a safety guardrail for a Telecom support system.
Your ONLY job is to check if the final answer gives instructions for a device
that is COMPLETELY UNRELATED to what the user asked about.

Rules:
1. If the user asked about Cisco and the answer discusses Cisco → PASS
2. If retrieved context includes multiple devices but the answer focuses on the queried device → PASS  
3. Only FAIL if the answer gives step-by-step instructions EXCLUSIVELY for a different device family
4. When in doubt → PASS

Respond ONLY in JSON:
{
  "passed": true | false,
  "reasoning": "<one sentence>",
  "offending_devices": []
}"""


def guardrail_node(state: RAGState) -> RAGState:
    """Ensure the answer doesn't give instructions for hardware not in scope."""
    logger.info("GUARDRAIL node")

    allowed_devices = state.get("mentioned_devices", [])

    try:
        llm = get_llm_client()
        response = llm.chat(
            system=GUARDRAIL_SYSTEM,
            user=(
                f"User Question: {state['query']}\n"
                f"Allowed Devices (from context): {', '.join(allowed_devices) if allowed_devices else 'None specified'}\n"
                f"Generated Answer:\n{state['generation']}"
            ),
            run_name="guardrail_checker"
        )

        parsed = _parse_json_response(response)
        passed = bool(parsed.get("passed", True))
        reasoning = parsed.get("reasoning", "")
        offending = parsed.get("offending_devices", [])

        decision = Decision.GUARDRAIL_PASS if passed else Decision.GUARDRAIL_FAIL
        entry = log_decision(state, "guardrail", decision, {
            "passed": passed,
            "allowed_devices": allowed_devices,
            "offending_devices": offending,
            "reasoning": reasoning
        })

        return {
            **state,
            "guardrail_passed": passed,
            "decision_log": state.get("decision_log", []) + [entry]
        }

    except Exception as e:
        logger.error("Guardrail check failed", error=str(e))
        entry = log_decision(state, "guardrail", "error", {"error": str(e)})
        return {
            **state,
            "guardrail_passed": True,  # fail-open on guardrail error
            "error": f"Guardrail error: {e}",
            "decision_log": state.get("decision_log", []) + [entry]
        }


# ---------------------------------------------------------------------------
# Node 7: Finalize Answer
# ---------------------------------------------------------------------------

def finalize_node(state: RAGState) -> RAGState:
    """Set the final answer based on all checks."""
    logger.info("FINALIZE node")

    if not state.get("guardrail_passed", True):
        final = (
            "⚠️ This answer was blocked by the safety guardrail because it contained "
            "instructions for hardware devices not mentioned in the original query context. "
            "Please ask about a specific supported device."
        )
    elif state.get("groundedness_score", 1.0) < 0.6 and state.get("generation"):
        final = (
            "⚠️ Note: The answer may contain information not fully supported by the source documents. "
            "Please verify with official documentation.\n\n" + state.get("generation", "")
        )
    else:
        final = state.get("generation", "No answer generated.")

    entry = log_decision(state, "finalize", "completed", {
        "answer_length": len(final),
        "guardrail_passed": state.get("guardrail_passed"),
        "groundedness_score": state.get("groundedness_score"),
        "relevance_score": state.get("relevance_score")
    })

    return {
        **state,
        "final_answer": final,
        "decision_log": state.get("decision_log", []) + [entry]
    }


# ---------------------------------------------------------------------------
# Routing functions (conditional edges)
# ---------------------------------------------------------------------------

def route_after_grading(state: RAGState) -> str:
    """Route based on relevance score."""
    score = state.get("relevance_score", 0.0)
    rewrite_count = state.get("rewrite_count", 0)

    if score >= settings.RELEVANCE_THRESHOLD:
        logger.info("Routing → GENERATE (relevant context)", score=score)
        return "generate"
    elif rewrite_count >= settings.MAX_REWRITE_ATTEMPTS:
        logger.warning("Max retries reached → GENERATE with partial context", rewrites=rewrite_count)
        return "generate"
    else:
        logger.info("Routing → REWRITE_QUERY (irrelevant context)", score=score, rewrites=rewrite_count)
        return "rewrite_query"


def route_after_groundedness(state: RAGState) -> str:
    """Route based on groundedness score."""
    score = state.get("groundedness_score", 1.0)
    if score >= 0.6:
        logger.info("Routing → GUARDRAIL (grounded)", score=score)
        return "guardrail"
    else:
        logger.warning("Routing → FINALIZE (hallucination detected)", score=score)
        return "finalize"


def route_after_guardrail(state: RAGState) -> str:
    """Route based on guardrail result."""
    passed = state.get("guardrail_passed", True)
    if passed:
        logger.info("Routing → FINALIZE (guardrail passed)")
        return "finalize"
    else:
        logger.warning("Routing → FINALIZE (guardrail FAILED)")
        return "finalize"


# ---------------------------------------------------------------------------
# Build and compile the LangGraph
# ---------------------------------------------------------------------------

def build_rag_graph() -> StateGraph:
    """Build the Corrective RAG state machine."""
    workflow = StateGraph(RAGState)

    # Add all nodes
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("grade_relevance", grade_relevance_node)
    workflow.add_node("rewrite_query", rewrite_query_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("check_groundedness", check_groundedness_node)
    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("finalize", finalize_node)

    # Set entry point
    workflow.set_entry_point("retrieve")

    # Add edges
    workflow.add_edge("retrieve", "grade_relevance")
    workflow.add_conditional_edges(
        "grade_relevance",
        route_after_grading,
        {
            "generate": "generate",
            "rewrite_query": "rewrite_query",
        }
    )
    workflow.add_edge("rewrite_query", "retrieve")  # Loop back
    workflow.add_edge("generate", "check_groundedness")
    workflow.add_conditional_edges(
        "check_groundedness",
        route_after_groundedness,
        {
            "guardrail": "guardrail",
            "finalize": "finalize",
        }
    )
    workflow.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {
            "finalize": "finalize",
        }
    )
    workflow.add_edge("finalize", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_rag_graph()
        logger.info("LangGraph compiled successfully")
    return _compiled_graph


async def run_rag_pipeline(query: str) -> dict:
    """
    Run the full Corrective RAG pipeline for a given query.
    Returns a structured result with answer, scores, and decision trace.
    """
    logger.info("Starting RAG pipeline", query=query[:100])

    initial_state: RAGState = {
        "query": query,
        "rewritten_query": "",
        "retrieved_docs": [],
        "relevant_docs": [],
        "generation": "",
        "relevance_score": 0.0,
        "groundedness_score": 0.0,
        "guardrail_passed": False,
        "rewrite_count": 0,
        "decision_log": [],
        "final_answer": "",
        "error": None,
        "mentioned_devices": []
    }

    try:
        graph = get_compiled_graph()
        final_state = await graph.ainvoke(initial_state)

        result = {
            "query": query,
            "final_answer": final_state.get("final_answer", ""),
            "scores": {
                "relevance": round(final_state.get("relevance_score", 0.0), 3),
                "groundedness": round(final_state.get("groundedness_score", 0.0), 3),
                "guardrail_passed": final_state.get("guardrail_passed", False),
            },
            "metadata": {
                "rewrite_count": final_state.get("rewrite_count", 0),
                "rewritten_query": final_state.get("rewritten_query", ""),
                "sources_used": [
                    {
                        "device": d.metadata.get("device"),
                        "category": d.metadata.get("category"),
                        "snippet": d.page_content[:150] + "..."
                    }
                    for d in (final_state.get("relevant_docs") or final_state.get("retrieved_docs", []))[:3]
                ],
                "mentioned_devices": final_state.get("mentioned_devices", []),
                "error": final_state.get("error")
            },
            "decision_trace": final_state.get("decision_log", [])
        }

        logger.info(
            "RAG pipeline completed",
            query=query[:60],
            relevance=result["scores"]["relevance"],
            groundedness=result["scores"]["groundedness"],
            guardrail=result["scores"]["guardrail_passed"],
            rewrites=result["metadata"]["rewrite_count"]
        )

        return result

    except Exception as e:
        logger.error("RAG pipeline failed", query=query[:80], error=str(e))
        return {
            "query": query,
            "final_answer": f"System error: {e}",
            "scores": {"relevance": 0.0, "groundedness": 0.0, "guardrail_passed": False},
            "metadata": {"error": str(e), "rewrite_count": 0, "sources_used": [], "mentioned_devices": []},
            "decision_trace": []
        }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """Extract and parse JSON from LLM response, stripping markdown fences."""
    text = text.strip()
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object with regex
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        logger.warning("Failed to parse JSON from LLM response", text=text[:200])
        return {}
