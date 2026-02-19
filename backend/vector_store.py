"""
Document ingestion and vector store management.
Uses ChromaDB with sentence-transformers for local embeddings.
"""
import json
import os
from typing import List, Optional
from langchain.schema import Document
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

from config import settings
from logger import get_logger

logger = get_logger("vector_store")


class VectorStoreManager:
    """Manages document ingestion and retrieval from ChromaDB."""

    def __init__(self):
        self.embeddings = None
        self.vectorstore = None
        self._initialize_embeddings()

    def _initialize_embeddings(self):
        """Initialize the embedding model (open-source, runs locally)."""
        try:
            logger.info("Initializing embedding model", model="all-MiniLM-L6-v2")
            self.embeddings = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True}
            )
            logger.info("Embedding model initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize embeddings", error=str(e))
            raise RuntimeError(f"Embedding initialization failed: {e}") from e

    def ingest_documents(self, data_path: str) -> int:
        """
        Load and ingest telecom manual documents into ChromaDB.
        Returns number of chunks ingested.
        """
        logger.info("Starting document ingestion", data_path=data_path)

        # Load raw documents
        try:
            with open(data_path, "r") as f:
                raw_docs = json.load(f)
        except FileNotFoundError:
            logger.error("Data file not found", path=data_path)
            raise
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in data file", error=str(e))
            raise

        # Convert to LangChain Documents with rich metadata
        documents = []
        for doc in raw_docs:
            lc_doc = Document(
                page_content=doc["content"],
                metadata={
                    "id": doc["id"],
                    "device": doc["device"],
                    "category": doc["category"],
                    "source": data_path
                }
            )
            documents.append(lc_doc)

        logger.info("Documents loaded", count=len(documents))

        # Split into chunks for better retrieval granularity
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        chunks = splitter.split_documents(documents)
        logger.info("Documents chunked", chunk_count=len(chunks))

        # Create/persist ChromaDB vectorstore
        try:
            self.vectorstore = Chroma.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                persist_directory=settings.CHROMA_PERSIST_DIR,
                collection_name=settings.COLLECTION_NAME
            )
            logger.info(
                "Vector store created",
                collection=settings.COLLECTION_NAME,
                persist_dir=settings.CHROMA_PERSIST_DIR,
                chunks_stored=len(chunks)
            )
            return len(chunks)
        except Exception as e:
            logger.error("Failed to create vector store", error=str(e))
            raise RuntimeError(f"Vector store creation failed: {e}") from e

    def load_existing(self) -> bool:
        """Load an existing ChromaDB collection if it exists."""
        if not os.path.exists(settings.CHROMA_PERSIST_DIR):
            logger.info("No existing vector store found")
            return False
        try:
            self.vectorstore = Chroma(
                persist_directory=settings.CHROMA_PERSIST_DIR,
                embedding_function=self.embeddings,
                collection_name=settings.COLLECTION_NAME
            )
            count = self.vectorstore._collection.count()
            if count == 0:
                logger.info("Existing vector store is empty")
                return False
            logger.info("Loaded existing vector store", document_count=count)
            return True
        except Exception as e:
            logger.warning("Failed to load existing vector store", error=str(e))
            return False

    def retrieve(self, query: str, k: int = None) -> List[Document]:
        """
        Retrieve top-k relevant documents for a query.
        Returns empty list on failure (fail-fast pattern).
        """
        if self.vectorstore is None:
            logger.error("Vector store not initialized - cannot retrieve")
            return []

        k = k or settings.TOP_K_RETRIEVAL
        try:
            results = self.vectorstore.similarity_search(query, k=k)
            logger.info(
                "Retrieval completed",
                query=query[:80],
                results_count=len(results),
                top_device=results[0].metadata.get("device") if results else None
            )
            return results
        except Exception as e:
            logger.error("Retrieval failed", query=query[:80], error=str(e))
            return []

    def retrieve_with_scores(self, query: str, k: int = None) -> List[tuple]:
        """Retrieve documents with similarity scores."""
        if self.vectorstore is None:
            return []
        k = k or settings.TOP_K_RETRIEVAL
        try:
            return self.vectorstore.similarity_search_with_score(query, k=k)
        except Exception as e:
            logger.error("Score-based retrieval failed", error=str(e))
            return []


# Singleton instance
_vector_store: Optional[VectorStoreManager] = None


def get_vector_store() -> VectorStoreManager:
    """Get or initialize the global VectorStoreManager."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStoreManager()
    return _vector_store


def initialize_vector_store(data_path: str = None) -> VectorStoreManager:
    """Initialize vector store: load existing or ingest new data."""
    global _vector_store
    _vector_store = VectorStoreManager()

    # Try loading existing first
    if _vector_store.load_existing():
        return _vector_store

    # Otherwise ingest fresh
    if data_path is None:
        data_path = os.path.join(os.path.dirname(__file__), "../data/telecom_manuals.json")

    _vector_store.ingest_documents(data_path)
    return _vector_store
