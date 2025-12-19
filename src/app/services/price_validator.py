"""
Price validation service.
Compares prices extracted from shelf images against database prices.
Uses Qdrant vector database for semantic fuzzy matching.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.config import settings
from app.services.qdrant_service import QdrantService, ProductMatch

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of price validation for a single product"""
    producto_imagen: str       # Product name from image
    precio_imagen: Optional[float]  # Price seen in image
    producto_sistema: Optional[str]  # Product name in database
    precio_sistema: Optional[float]  # Price in database
    validacion: str            # ✅, ❌, or ⚠️
    diferencia: Optional[float]  # Price difference
    status: str                # MATCH, PRICE_DIFF, NOT_FOUND, NO_PRICE
    match_score: Optional[float] = None  # Similarity score (0-1)


class PriceValidator:
    """
    Validates prices from shelf images against Qdrant vector database.
    Uses semantic search for intelligent fuzzy matching.
    """
    
    def __init__(self, qdrant_service: QdrantService):
        self.qdrant = qdrant_service
        self.tolerance = settings.PRICE_TOLERANCE_PERCENT / 100
        self.search_limit = settings.SEARCH_LIMIT
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD
        logger.info(f"✅ PriceValidator initialized with {settings.PRICE_TOLERANCE_PERCENT}% tolerance")
    
    async def validate_products(
        self,
        productos_imagen: List[Dict[str, Any]],
        tienda_id: int
    ) -> List[ValidationResult]:
        """
        Validate all products from an image against the Qdrant database.
        
        Uses semantic search:
        1. Generate embeddings for detected product names
        2. Search for similar products in Qdrant (filtered by store)
        3. Compare prices of best matches
        
        Args:
            productos_imagen: Products extracted from image
            tienda_id: Store ID to filter results
            
        Returns:
            List of ValidationResult for each product
        """
        logger.info(f"🔍 Validating {len(productos_imagen)} products for store {tienda_id}")
        
        validaciones = []
        
        # Extract product names for batch search
        queries = [p.get("nombre", "") for p in productos_imagen]
        
        # Batch search in Qdrant
        search_results = await self.qdrant.search_products_batch(
            queries=queries,
            tienda_id=str(tienda_id),
            limit=self.search_limit,
            score_threshold=self.similarity_threshold
        )
        
        for producto in productos_imagen:
            nombre_imagen = producto.get("nombre", "DESCONOCIDO")
            precio_imagen = producto.get("precio")
            
            # Get matches for this product
            matches = search_results.get(nombre_imagen, [])
            
            if not matches:
                # Product not found in database
                validaciones.append(ValidationResult(
                    producto_imagen=nombre_imagen,
                    precio_imagen=precio_imagen,
                    producto_sistema=None,
                    precio_sistema=None,
                    validacion="⚠️",
                    diferencia=None,
                    status="NOT_FOUND",
                    match_score=None
                ))
                continue
            
            # Use best match (highest similarity score)
            best_match = matches[0]
            precio_sistema = best_match.precio
            nombre_sistema = best_match.nombre
            match_score = best_match.score
            
            # Compare prices
            validation_result = self._compare_prices(precio_imagen, precio_sistema)
            
            validaciones.append(ValidationResult(
                producto_imagen=nombre_imagen,
                precio_imagen=precio_imagen,
                producto_sistema=nombre_sistema,
                precio_sistema=precio_sistema,
                validacion=validation_result["validacion"],
                diferencia=validation_result["diferencia"],
                status=validation_result["status"],
                match_score=match_score
            ))
        
        # Log summary
        self._log_summary(validaciones)
        
        return validaciones
    
    def _compare_prices(
        self, 
        precio_imagen: Optional[float], 
        precio_sistema: Optional[float]
    ) -> Dict[str, Any]:
        """Compare two prices and return validation result"""
        
        if precio_imagen is None or precio_sistema is None:
            return {
                "validacion": "⚠️",
                "diferencia": None,
                "status": "NO_PRICE"
            }
        
        diferencia = precio_sistema - precio_imagen
        
        if self._prices_match(precio_imagen, precio_sistema):
            return {
                "validacion": "✅",
                "diferencia": diferencia,
                "status": "MATCH"
            }
        else:
            return {
                "validacion": "❌",
                "diferencia": diferencia,
                "status": "PRICE_DIFF"
            }
    
    def _prices_match(self, precio_imagen: float, precio_sistema: float) -> bool:
        """Check if prices match within tolerance"""
        if precio_sistema == 0:
            return precio_imagen == 0
        
        diff_percent = abs(precio_imagen - precio_sistema) / precio_sistema
        return diff_percent <= self.tolerance
    
    def _log_summary(self, validaciones: List[ValidationResult]):
        """Log validation summary"""
        matches = sum(1 for v in validaciones if v.status == "MATCH")
        diffs = sum(1 for v in validaciones if v.status == "PRICE_DIFF")
        not_found = sum(1 for v in validaciones if v.status == "NOT_FOUND")
        no_price = sum(1 for v in validaciones if v.status == "NO_PRICE")
        
        logger.info(
            f"📊 Validation complete: "
            f"✅ {matches} correct | "
            f"❌ {diffs} price diff | "
            f"⚠️ {not_found} not found | "
            f"❔ {no_price} no price"
        )
    
    def _deduplicate_results(
        self, 
        validaciones: List[ValidationResult]
    ) -> List[ValidationResult]:
        """
        Remove duplicate products from results.
        Keeps the first occurrence of each unique product (by sistema name or imagen name).
        """
        seen = set()
        unique = []
        
        for v in validaciones:
            # Use sistema name if available, otherwise imagen name
            key = v.producto_sistema if v.producto_sistema else v.producto_imagen
            key = key.upper().strip() if key else ""
            
            # Skip empty or NULL names
            if not key or key == "NULL" or key == "NONE":
                continue
            
            if key not in seen:
                seen.add(key)
                unique.append(v)
        
        return unique
    
    def format_results_for_slack(
        self, 
        validaciones: List[ValidationResult],
        tienda_id: int
    ) -> str:
        """
        Format validation results as Slack message.
        Matches the exact format from n8n workflow.
        """
        if not validaciones:
            return "⚠️ No se encontraron productos en la imagen."
        
        # Deduplicar productos
        validaciones = self._deduplicate_results(validaciones)
        
        if not validaciones:
            return "⚠️ No se encontraron productos válidos en la imagen."
        
        # Construir tabla
        lines = [
            f"*Resultados de validación - Tienda {tienda_id}*",
            "",
            "```",
            f"{'#':<4} {'PRODUCTO':<45} {'PRECIO FOTO':>12} {'PRECIO SISTEMA':>15} {'VALIDACION':>11}",
            "-" * 92
        ]
        
        for i, v in enumerate(validaciones, 1):
            # Usar nombre del sistema si está disponible, sino el de la imagen
            nombre = v.producto_sistema if v.producto_sistema else v.producto_imagen
            nombre = nombre[:44] if len(nombre) > 44 else nombre
            
            # Formatear precios
            p_foto = f"${v.precio_imagen:.2f}" if v.precio_imagen is not None else "N/A"
            p_sistema = f"${v.precio_sistema:.2f}" if v.precio_sistema is not None else "N/A"
            
            # Validación: ✅ correcto, ❌ diferencia, ⚠️ no encontrado
            val_symbol = v.validacion
            
            lines.append(
                f"{i:<4} {nombre:<45} {p_foto:>12} {p_sistema:>15} {val_symbol:>11}"
            )
        
        lines.append("```")
        
        # Resumen (basado en lista deduplicada)
        matches = sum(1 for v in validaciones if v.status == "MATCH")
        diffs = sum(1 for v in validaciones if v.status == "PRICE_DIFF")
        not_found = sum(1 for v in validaciones if v.status in ("NOT_FOUND", "NO_PRICE"))
        total = len(validaciones)
        
        lines.append("")
        lines.append(
            f"*Resumen:* ✅ {matches} correctos | "
            f"❌ {diffs} con diferencia | "
            f"⚠️ {not_found} no encontrados | "
            f"Total: {total} productos"
        )
        
        return "\n".join(lines)
