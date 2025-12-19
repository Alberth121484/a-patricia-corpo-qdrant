"""
Qdrant service for the Web Admin.
Manages product indexing and deletion.
"""
import logging
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy load embedding model
_embedding_model = None
_embedding_dim = 384


def get_embedding_model():
    """Lazy load the embedding model"""
    global _embedding_model, _embedding_dim
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: paraphrase-multilingual-MiniLM-L12-v2")
        _embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        _embedding_dim = _embedding_model.get_sentence_embedding_dimension()
        logger.info(f"✅ Embedding model loaded (dim={_embedding_dim})")
    return _embedding_model


class QdrantAdminService:
    """
    Service for managing products in Qdrant vector database.
    Used by the Web Admin for indexing and deletion.
    """
    
    COLLECTION_NAME = "products"
    
    def __init__(self):
        """Initialize Qdrant client"""
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=60
        )
        self._ensure_collection()
        logger.info(f"✅ QdrantAdminService initialized")
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist"""
        global _embedding_dim
        
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.COLLECTION_NAME not in collection_names:
            # Load model to get dimension
            get_embedding_model()
            
            logger.info(f"Creating collection: {self.COLLECTION_NAME}")
            self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=_embedding_dim,
                    distance=Distance.COSINE
                )
            )
            
            # Create payload indexes
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
    
    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts"""
        model = get_embedding_model()
        
        # Normalize texts
        normalized = [t.upper().strip() if t else "" for t in texts]
        
        # Generate embeddings
        embeddings = model.encode(normalized, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()
    
    async def index_products(
        self,
        products: List[Dict[str, Any]],
        file_id: str
    ) -> Dict[str, Any]:
        """
        Index products into Qdrant.
        
        Args:
            products: List of product dicts
            file_id: Source file ID for tracking
            
        Returns:
            Indexing statistics
        """
        if not products:
            return {"indexed": 0, "errors": 0}
        
        # Extract names for embedding
        names = [p.get("nombre", "") for p in products]
        
        # Generate embeddings in batch
        logger.info(f"Generating embeddings for {len(names)} products...")
        embeddings = self._generate_embeddings(names)
        
        # Create points
        points = []
        errors = 0
        
        for i, (product, embedding) in enumerate(zip(products, embeddings)):
            try:
                point_id = f"{file_id}_{i}"
                
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
            except Exception as e:
                logger.error(f"Error creating point {i}: {e}")
                errors += 1
        
        # Upsert in batches
        batch_size = 100
        indexed = 0
        
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            try:
                self.client.upsert(
                    collection_name=self.COLLECTION_NAME,
                    points=batch
                )
                indexed += len(batch)
            except Exception as e:
                logger.error(f"Error upserting batch {i}: {e}")
                errors += len(batch)
        
        logger.info(f"Indexed {indexed} products from file {file_id}")
        
        return {
            "indexed": indexed,
            "errors": errors,
            "file_id": file_id
        }
    
    async def delete_by_file(self, file_id: str) -> int:
        """
        Delete all products from a specific file.
        
        Args:
            file_id: File ID to delete
            
        Returns:
            Number of products deleted
        """
        # Count before delete
        try:
            count_result = self.client.count(
                collection_name=self.COLLECTION_NAME,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="file_id",
                            match=MatchValue(value=file_id)
                        )
                    ]
                )
            )
            count_before = count_result.count
        except Exception:
            count_before = 0
        
        # Delete points
        try:
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
        except Exception as e:
            logger.error(f"Error deleting products: {e}")
            return 0
        
        return count_before
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        try:
            info = self.client.get_collection(self.COLLECTION_NAME)
            return {
                "total_products": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.value
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                "total_products": 0,
                "vectors_count": 0,
                "status": "error"
            }
    
    async def get_products_by_file(
        self, 
        file_id: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get products indexed from a specific file"""
        try:
            results, _ = self.client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="file_id",
                            match=MatchValue(value=file_id)
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            return [point.payload for point in results]
        except Exception as e:
            logger.error(f"Error getting products: {e}")
            return []
    
    async def count_by_file(self, file_id: str) -> int:
        """Count products from a specific file"""
        try:
            result = self.client.count(
                collection_name=self.COLLECTION_NAME,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="file_id",
                            match=MatchValue(value=file_id)
                        )
                    ]
                )
            )
            return result.count
        except Exception:
            return 0
    
    async def get_unique_file_ids(self) -> List[str]:
        """Get list of unique file IDs in the collection"""
        try:
            # Scroll through all points to get unique file_ids
            file_ids = set()
            offset = None
            
            while True:
                results, offset = self.client.scroll(
                    collection_name=self.COLLECTION_NAME,
                    limit=1000,
                    offset=offset,
                    with_payload=["file_id"],
                    with_vectors=False
                )
                
                for point in results:
                    if point.payload and point.payload.get("file_id"):
                        file_ids.add(point.payload["file_id"])
                
                if offset is None:
                    break
            
            return list(file_ids)
        except Exception as e:
            logger.error(f"Error getting file IDs: {e}")
            return []
