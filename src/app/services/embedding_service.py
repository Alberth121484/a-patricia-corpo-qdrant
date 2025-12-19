"""
Embedding service using sentence-transformers for semantic search.
Generates vector embeddings for product names to enable fuzzy matching.
"""
import logging
from typing import List, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Lazy load to avoid loading model on import
_model = None
_model_name = "paraphrase-multilingual-MiniLM-L12-v2"


def get_model():
    """Lazy load the embedding model"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {_model_name}")
        _model = SentenceTransformer(_model_name)
        logger.info("✅ Embedding model loaded successfully")
    return _model


class EmbeddingService:
    """
    Service for generating text embeddings using sentence-transformers.
    Uses multilingual model for Spanish product names.
    """
    
    def __init__(self):
        """Initialize embedding service"""
        self.model = get_model()
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        logger.info(f"✅ EmbeddingService initialized (dim={self.embedding_dim})")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for a single text.
        
        Args:
            text: Text to embed (product name, description, etc.)
            
        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            return [0.0] * self.embedding_dim
        
        # Normalize text
        text = self._normalize_text(text)
        
        # Generate embedding
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch (more efficient).
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Normalize all texts
        normalized = [self._normalize_text(t) for t in texts]
        
        # Generate embeddings in batch
        embeddings = self.model.encode(normalized, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for better embedding quality.
        
        Args:
            text: Raw text
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Convert to uppercase (consistency with product names)
        text = text.upper().strip()
        
        # Remove extra whitespace
        text = " ".join(text.split())
        
        return text
    
    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score between 0 and 1
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
