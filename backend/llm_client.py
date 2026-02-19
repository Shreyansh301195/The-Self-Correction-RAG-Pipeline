"""
LLM client module.
Supports OpenAI-compatible APIs (OpenAI, OpenRouter, LM Studio, Ollama).
For open-source models, configure OPENAI_BASE_URL to point to OpenRouter or local server.
"""
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.schema import BaseMessage, HumanMessage, SystemMessage

from config import settings
from logger import get_logger

logger = get_logger("llm_client")


class LLMClient:
    """
    Wrapper around LangChain ChatOpenAI supporting any OpenAI-compatible backend.
    
    For open-source models via OpenRouter:
      OPENAI_BASE_URL=https://openrouter.ai/api/v1
      LLM_MODEL=mistralai/mistral-7b-instruct
      OPENAI_API_KEY=<your-openrouter-key>
    
    For local Ollama:
      OPENAI_BASE_URL=http://localhost:11434/v1
      LLM_MODEL=llama3
      OPENAI_API_KEY=ollama
    """

    def __init__(self, temperature: float = 0.0):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be set in environment variables")

        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=temperature,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            max_retries=3,
            request_timeout=60,
        )
        logger.info(
            "LLM client initialized",
            model=settings.LLM_MODEL,
            base_url=settings.OPENAI_BASE_URL,
            temperature=temperature
        )

    def invoke(self, messages: list[BaseMessage], run_name: str = None) -> str:
        """Invoke the LLM with a list of messages. Returns text content."""
        try:
            kwargs = {}
            if run_name:
                kwargs["config"] = {"run_name": run_name}
            response = self.llm.invoke(messages, **kwargs)
            return response.content.strip()
        except Exception as e:
            logger.error("LLM invocation failed", error=str(e), run_name=run_name)
            raise RuntimeError(f"LLM call failed: {e}") from e

    def chat(self, system: str, user: str, run_name: str = None) -> str:
        """Convenience method for system + user message pattern."""
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
        return self.invoke(messages, run_name=run_name)


# Singleton
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
