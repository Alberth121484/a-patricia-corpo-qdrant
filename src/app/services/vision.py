"""
Vision service using Gemini for shelf image analysis.
Extracts product names and prices from store shelf photos.
"""
import asyncio
import logging
import json
import re
from typing import List, Dict, Any, Optional, Tuple

import httpx
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from app.config import settings

logger = logging.getLogger(__name__)


class VisionService:
    """
    Service for analyzing shelf images using Gemini Vision.
    Replicates the functionality of the n8n "Analyze image" node.
    """
    
    # Prompt optimizado para extraer productos de estantes
    # Basado en el prompt original de n8n pero mejorado
    EXTRACTION_PROMPT = """Analiza la imagen de un estante de un supermercado.
Tu tarea es:

1. Identificar los productos visibles en el estante (nombre del producto o marca cuando sea legible).
2. Clasificarlos por categorías (ej. analgésicos, antiácidos, electrolitos, lácteos, etc.).
3. Extraer los precios asociados a cada producto y relacionarlos correctamente.
4. Recorrer estante por estante producto por producto y no omitir ninguno.
5. Señalar si hay productos repetidos o en diferentes presentaciones.
6. Detectar espacios vacíos en el estante que indiquen productos agotados.

IMPORTANTE:
- Extrae el nombre del producto lo más completo posible incluyendo marca, variedad y tamaño.
- Los precios deben ser números decimales (ej: 25.50, no "$25.50").
- Si no puedes leer el precio, usa null.
- NO omitas ningún producto visible.

Retorna ÚNICAMENTE un JSON válido con la siguiente estructura (sin markdown, sin ```):
[
  {
    "categoria": "Nombre de la categoría",
    "productos": [
      {
        "nombre": "NOMBRE COMPLETO DEL PRODUCTO EN MAYÚSCULAS",
        "precio": 25.50,
        "presentacion": "500g o tamaño si aplica",
        "observaciones": "espacio vacío, varias versiones, etc. o null"
      }
    ]
  }
]

Solo retorna el JSON puro, nada más."""

    def __init__(self):
        """Initialize Gemini client"""
        self._configure_gemini()
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        
        # Configuración de seguridad permisiva para analizar cualquier imagen
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        logger.info(f"✅ VisionService initialized with model: {settings.GEMINI_MODEL}")
    
    def _configure_gemini(self):
        """Configure Gemini API credentials"""
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            logger.info("Gemini configured with API key")
        elif settings.GOOGLE_APPLICATION_CREDENTIALS_JSON:
            # Para service account, necesitamos usar el método de autenticación de Google
            creds = settings.get_gcp_credentials()
            if creds:
                genai.configure(api_key=creds.get("api_key") if "api_key" in creds else None)
                logger.info("Gemini configured with service account")
        else:
            raise ValueError("No Gemini API key or Google credentials provided")
    
    async def download_image_from_slack(self, url: str, bot_token: str) -> bytes:
        """
        Download image from Slack private URL.
        Slack requires authentication to access private file URLs.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {bot_token}"},
                follow_redirects=True,
                timeout=60.0
            )
            response.raise_for_status()
            logger.info(f"✅ Downloaded image: {len(response.content)} bytes")
            return response.content
    
    async def analyze_shelf_image(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Analyze shelf image and extract products with prices.
        
        Returns:
            List of products with: nombre, precio, presentacion, categoria
        """
        try:
            # Detectar tipo de imagen
            mime_type = self._detect_mime_type(image_bytes)
            
            # Crear parte de imagen para Gemini
            image_part = {
                "mime_type": mime_type,
                "data": image_bytes
            }
            
            # Generar contenido con Gemini
            logger.info("🔍 Analyzing image with Gemini...")
            response = await asyncio.to_thread(
                self.model.generate_content,
                [self.EXTRACTION_PROMPT, image_part],
                safety_settings=self.safety_settings,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
                }
            )
            
            # Parsear respuesta
            text = response.text.strip()
            products = self._parse_gemini_response(text)
            
            # Deduplicar productos
            products = self._deduplicate_products(products)
            
            logger.info(f"✅ Extracted {len(products)} unique products from image")
            return products
            
        except Exception as e:
            logger.error(f"❌ Vision analysis failed: {e}", exc_info=True)
            raise
    
    async def analyze_shelf_image_with_tokens(self, image_bytes: bytes) -> Tuple[List[Dict[str, Any]], int]:
        """
        Analyze shelf image and extract products with prices.
        Also returns token usage for metrics.
        
        Returns:
            Tuple of (products list, tokens used)
        """
        try:
            # Detectar tipo de imagen
            mime_type = self._detect_mime_type(image_bytes)
            
            # Crear parte de imagen para Gemini
            image_part = {
                "mime_type": mime_type,
                "data": image_bytes
            }
            
            # Generar contenido con Gemini
            logger.info("🔍 Analyzing image with Gemini...")
            response = await asyncio.to_thread(
                self.model.generate_content,
                [self.EXTRACTION_PROMPT, image_part],
                safety_settings=self.safety_settings,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
                }
            )
            
            # Extract token usage
            tokens_used = 0
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                tokens_used = getattr(usage, 'total_token_count', 0) or 0
                logger.info(f"📊 Tokens used: {tokens_used}")
            
            # Parsear respuesta
            text = response.text.strip()
            products = self._parse_gemini_response(text)
            
            # Deduplicar productos
            products = self._deduplicate_products(products)
            
            logger.info(f"✅ Extracted {len(products)} unique products from image")
            return products, tokens_used
            
        except Exception as e:
            logger.error(f"❌ Vision analysis failed: {e}", exc_info=True)
            raise
    
    def _detect_mime_type(self, image_bytes: bytes) -> str:
        """Detect image MIME type from bytes"""
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        elif image_bytes[:2] == b'\xff\xd8':
            return "image/jpeg"
        elif image_bytes[:6] in (b'GIF87a', b'GIF89a'):
            return "image/gif"
        elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            return "image/webp"
        else:
            return "image/jpeg"  # Default
    
    def _parse_gemini_response(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse Gemini response and flatten products.
        Handles both array format and single object format.
        Robust against truncated/malformed JSON.
        """
        # Limpiar respuesta de markdown si viene
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()
        
        data = None
        
        # Intento 1: Parse directo
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Direct JSON parse failed: {e}")
            
            # Intento 2: Reparar JSON truncado
            data = self._repair_truncated_json(text)
            
            if data is None:
                # Intento 3: Extraer productos con regex
                logger.info("Attempting regex extraction...")
                return self._extract_products_regex(text)
        
        if data is None:
            logger.error("All parsing attempts failed")
            return []
        
        # Normalizar: si no es array, convertir a array
        if not isinstance(data, list):
            data = [data]
        
        # Aplanar estructura de categorías -> productos
        productos_flat = []
        
        for seccion in data:
            if not isinstance(seccion, dict):
                continue
                
            categoria = seccion.get("categoria", "General")
            productos = seccion.get("productos", [])
            
            if not productos and "nombre" in seccion:
                # Es un producto directo, no una categoría
                productos = [seccion]
                categoria = seccion.get("categoria", "General")
            
            for producto in productos:
                if not isinstance(producto, dict):
                    continue
                    
                nombre = str(producto.get("nombre", "")).upper().strip()
                if nombre and nombre != "NULL":
                    productos_flat.append({
                        "nombre": nombre,
                        "precio": self._parse_price(producto.get("precio")),
                        "presentacion": producto.get("presentacion", ""),
                        "categoria": categoria,
                        "observaciones": producto.get("observaciones")
                    })
        
        return productos_flat
    
    def _repair_truncated_json(self, text: str) -> Optional[List]:
        """
        Attempt to repair truncated JSON by closing brackets/braces.
        """
        # Contar brackets abiertos
        open_brackets = text.count('[') - text.count(']')
        open_braces = text.count('{') - text.count('}')
        
        # Intentar cerrar
        repaired = text.rstrip().rstrip(',')  # Quitar trailing comma
        repaired += '}' * open_braces
        repaired += ']' * open_brackets
        
        try:
            data = json.loads(repaired)
            logger.info("✅ JSON repaired successfully")
            return data
        except json.JSONDecodeError:
            # Intentar otra reparación más agresiva
            # Buscar el último objeto completo
            last_complete = text.rfind('},')
            if last_complete > 0:
                truncated = text[:last_complete + 1]
                # Cerrar arrays y objetos abiertos
                open_brackets = truncated.count('[') - truncated.count(']')
                open_braces = truncated.count('{') - truncated.count('}')
                truncated += '}' * max(0, open_braces)
                truncated += ']' * max(0, open_brackets)
                
                try:
                    data = json.loads(truncated)
                    logger.info(f"✅ JSON repaired by truncation (kept until last complete object)")
                    return data
                except:
                    pass
        
        return None
    
    def _extract_products_regex(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract products using regex when JSON parsing fails completely.
        Looks for patterns like: "nombre": "...", "precio": ...
        """
        productos = []
        
        # Pattern to match product objects
        pattern = r'"nombre"\s*:\s*"([^"]+)"[^}]*?"precio"\s*:\s*(\d+(?:\.\d+)?)'
        
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        for nombre, precio in matches:
            try:
                productos.append({
                    "nombre": nombre.upper().strip(),
                    "precio": float(precio),
                    "presentacion": "",
                    "categoria": "General",
                    "observaciones": None
                })
            except (ValueError, TypeError):
                continue
        
        if productos:
            logger.info(f"✅ Extracted {len(productos)} products via regex")
        else:
            logger.warning("Regex extraction found no products")
        
        return productos
    
    def _deduplicate_products(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate products based on name.
        Keeps first occurrence of each unique product.
        Also filters out invalid entries (NULL, NONE, empty names).
        """
        seen = set()
        unique = []
        
        for p in products:
            nombre = p.get("nombre", "").upper().strip()
            
            # Skip invalid names
            if not nombre or nombre in ("NULL", "NONE", "NO VISIBLE", "NO LEGIBLE"):
                continue
            
            # Create a key based on name (normalized)
            # Remove common variations to catch more duplicates
            key = re.sub(r'\s+', ' ', nombre)  # Normalize spaces
            
            if key not in seen:
                seen.add(key)
                unique.append(p)
        
        if len(products) != len(unique):
            logger.info(f"🔄 Deduplicated: {len(products)} -> {len(unique)} products")
        
        return unique
    
    def _parse_price(self, price: Any) -> Optional[float]:
        """Parse price from various formats to float"""
        if price is None or price == "No visible" or price == "null":
            return None
        
        if isinstance(price, (int, float)):
            return float(price)
        
        if isinstance(price, str):
            # Remover símbolos de moneda y espacios
            cleaned = re.sub(r'[^\d.]', '', price)
            try:
                return float(cleaned) if cleaned else None
            except ValueError:
                return None
        
        return None
