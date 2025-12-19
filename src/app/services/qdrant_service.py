"""
Qdrant service for vector database operations.
Replaces BigQuery with semantic search capabilities.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from app.config import settings
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class ProductMatch:
    """Represents a product match from vector search"""
    id: str
    nombre: str
    precio: float
    tienda_id: str
    codigo: Optional[str] = None
    categoria: Optional[str] = None
    presentacion: Optional[str] = None
    score: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class QdrantService:
    """
    Service for managing product data in Qdrant vector database.
    Provides semantic search capabilities for fuzzy product matching.
    """
    
    COLLECTION_NAME = "products"
    
    def __init__(self):
        """Initialize Qdrant client and embedding service"""
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=30
        )
        self.embedding_service = EmbeddingService()
        self._ensure_collection()
        logger.info(f"✅ QdrantService initialized (host={settings.QDRANT_HOST}:{settings.QDRANT_PORT})")
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist"""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.COLLECTION_NAME not in collection_names:
            logger.info(f"Creating collection: {self.COLLECTION_NAME}")
            self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.embedding_service.embedding_dim,
                    distance=Distance.COSINE
                )
            )
            
            # Create payload indexes for filtering
            self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="tienda_id",
                field_schema="keyword"
            )
            self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="file_id",
                field_schema="keyword"
            )
            logger.info(f"✅ Collection '{self.COLLECTION_NAME}' created")
        else:
            logger.info(f"Collection '{self.COLLECTION_NAME}' already exists")
    
    async def search_products(
        self,
        query: str,
        tienda_id: Optional[str] = None,
        limit: int = 5,
        score_threshold: float = 0.5
    ) -> List[ProductMatch]:
        """
        Search for products using semantic similarity.
        
        Args:
            query: Product name to search for
            tienda_id: Optional store ID to filter results
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of ProductMatch objects sorted by similarity
        """
        # Generate embedding for query
        query_embedding = self.embedding_service.generate_embedding(query)
        
        # Build filter if tienda_id provided
        search_filter = None
        if tienda_id:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="tienda_id",
                        match=MatchValue(value=str(tienda_id))
                    )
                ]
            )
        
        # Search in Qdrant
        results = self.client.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=limit,
            score_threshold=score_threshold
        )
        
        # Convert to ProductMatch objects
        matches = []
        for hit in results:
            payload = hit.payload or {}
            match = ProductMatch(
                id=str(hit.id),
                nombre=payload.get("nombre", ""),
                precio=float(payload.get("precio", 0)),
                tienda_id=str(payload.get("tienda_id", "")),
                codigo=payload.get("codigo"),
                categoria=payload.get("categoria"),
                presentacion=payload.get("presentacion"),
                score=hit.score,
                metadata=payload
            )
            matches.append(match)
        
        logger.debug(f"Search '{query}' returned {len(matches)} results")
        return matches
    
    async def search_products_batch(
        self,
        queries: List[str],
        tienda_id: Optional[str] = None,
        limit: int = 3,
        score_threshold: float = 0.5
    ) -> Dict[str, List[ProductMatch]]:
        """
        Search for multiple products in batch.
        
        Args:
            queries: List of product names to search
            tienda_id: Optional store ID to filter results
            limit: Maximum results per query
            score_threshold: Minimum similarity score
            
        Returns:
            Dictionary mapping query -> list of matches
        """
        results = {}
        
        # Generate all embeddings in batch
        embeddings = self.embedding_service.generate_embeddings_batch(queries)
        
        # Build filter
        search_filter = None
        if tienda_id:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="tienda_id",
                        match=MatchValue(value=str(tienda_id))
                    )
                ]
            )
        
        # Search for each query
        for query, embedding in zip(queries, embeddings):
            hits = self.client.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=embedding,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold
            )
            
            matches = []
            for hit in hits:
                payload = hit.payload or {}
                match = ProductMatch(
                    id=str(hit.id),
                    nombre=payload.get("nombre", ""),
                    precio=float(payload.get("precio", 0)),
                    tienda_id=str(payload.get("tienda_id", "")),
                    codigo=payload.get("codigo"),
                    categoria=payload.get("categoria"),
                    presentacion=payload.get("presentacion"),
                    score=hit.score,
                    metadata=payload
                )
                matches.append(match)
            
            results[query] = matches
        
        return results
    
    async def add_products(
        self,
        products: List[Dict[str, Any]],
        file_id: str
    ) -> int:
        """
        Add products to the vector database.
        
        Args:
            products: List of product dictionaries with keys:
                - nombre: Product name (required)
                - precio: Product price (required)
                - tienda_id: Store ID (required)
                - codigo: Product code (optional)
                - categoria: Category (optional)
                - presentacion: Size/presentation (optional)
            file_id: ID of the source file for tracking
            
        Returns:
            Number of products added
        """
        if not products:
            return 0
        
        # Extract names for batch embedding
        names = [p.get("nombre", "") for p in products]
        embeddings = self.embedding_service.generate_embeddings_batch(names)
        
        # Create points
        points = []
        for i, (product, embedding) in enumerate(zip(products, embeddings)):
            # Generate unique ID
            point_id = f"{file_id}_{i}"
            
            # Build payload
            payload = {
                "nombre": product.get("nombre", ""),
                "precio": float(product.get("precio", 0)),
                "tienda_id": str(product.get("tienda_id", "")),
                "codigo": product.get("codigo"),
                "categoria": product.get("categoria"),
                "presentacion": product.get("presentacion"),
                "file_id": file_id
            }
            
            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            ))
        
        # Upsert in batches
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=batch
            )
        
        logger.info(f"Added {len(points)} products from file {file_id}")
        return len(points)
    
    async def delete_by_file(self, file_id: str) -> int:
        """
        Delete all products from a specific file.
        
        Args:
            file_id: ID of the file whose products should be deleted
            
        Returns:
            Number of points deleted
        """
        # Count before delete
        count_before = self.client.count(
            collection_name=self.COLLECTION_NAME,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="file_id",
                        match=MatchValue(value=file_id)
                    )
                ]
            )
        ).count
        
        # Delete points
        self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="file_id",
                            match=MatchValue(value=file_id)
                        )
                    ]
                )
            )
        )
        
        logger.info(f"Deleted {count_before} products from file {file_id}")
        return count_before
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection"""
        info = self.client.get_collection(self.COLLECTION_NAME)
        return {
            "total_points": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value
        }
    
    async def get_products_by_tienda(self, tienda_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get all products for a specific store.
        
        Args:
            tienda_id: Store ID
            limit: Maximum products to return
            
        Returns:
            List of product dictionaries
        """
        results, _ = self.client.scroll(
            collection_name=self.COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="tienda_id",
                        match=MatchValue(value=str(tienda_id))
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False
        )
        
        return [point.payload for point in results]
