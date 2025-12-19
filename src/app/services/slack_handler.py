"""
Slack event handlers.
Processes messages from Slack and routes them to appropriate services.
Uses Qdrant for semantic product search.
"""
import asyncio
import logging
import re
from typing import Optional, Set

from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from app.config import settings
from app.services.vision import VisionService
from app.services.price_validator import PriceValidator

logger = logging.getLogger(__name__)


class SlackHandler:
    """
    Handles Slack events and messages.
    Implements the same flow as the n8n AgentePatricia workflow:
    1. Receive message with image
    2. Add "eyes" reaction
    3. Process image and validate prices
    4. Remove "eyes", add "white_check_mark"
    5. Send results
    """
    
    def __init__(
        self,
        slack_app: AsyncApp,
        vision_service: VisionService,
        price_validator: PriceValidator
    ):
        self.slack_app = slack_app
        self.vision = vision_service
        self.validator = price_validator
        self.processing_messages: Set[str] = set()  # Prevent duplicate processing
        
        logger.info("✅ SlackHandler initialized")
    
    def register_handlers(self):
        """Register all Slack event handlers"""
        
        @self.slack_app.event("message")
        async def handle_message(event, say, client: AsyncWebClient):
            """Handle direct messages and channel messages"""
            # Ignore ALL bot messages (including our own)
            if event.get("bot_id"):
                return
            
            # Ignore messages from bots (alternative check)
            if event.get("bot_profile"):
                return
            
            # Ignore message_changed, message_deleted, and other subtypes except file_share
            subtype = event.get("subtype")
            if subtype and subtype not in ["file_share"]:
                return
            
            # Final safety check - ignore if no user
            if not event.get("user"):
                return
            
            await self._process_message(event, say, client)
        
        # Note: app_mention events are already captured by the message event handler
        # so we don't need a separate handler for mentions
        
        logger.info("✅ Slack event handlers registered")
    
    async def _process_message(
        self, 
        event: dict, 
        say, 
        client: AsyncWebClient
    ):
        """
        Process incoming Slack message.
        Detects if it contains an image and processes accordingly.
        """
        message_ts = event.get("ts", "")
        channel = event.get("channel")
        user = event.get("user")
        
        # Prevent duplicate processing (Slack can send same event multiple times)
        if message_ts in self.processing_messages:
            logger.debug(f"Skipping duplicate message: {message_ts}")
            return
        
        # Check if user is allowed (if restriction is configured)
        allowed_users = settings.get_allowed_users()
        if allowed_users and user not in allowed_users:
            logger.info(f"User {user} not in allowed list, ignoring")
            return
        
        self.processing_messages.add(message_ts)
        
        try:
            text = event.get("text", "")
            files = event.get("files", [])
            subtype = event.get("subtype", "")
            
            # Log event details for debugging
            logger.info(f"📨 Message received - User: {user}, Channel: {channel}")
            logger.info(f"   Text: {text[:100] if text else 'None'}...")
            logger.info(f"   Subtype: {subtype}, Files count: {len(files)}")
            
            # Check if there's an image file
            image_file = self._find_image_file(files)
            
            if image_file:
                logger.info(f"🖼️ Image detected: {image_file.get('name', 'unknown')}")
                # Process image for price validation
                await self._handle_image_analysis(
                    event=event,
                    image_file=image_file,
                    text=text,
                    channel=channel,
                    user=user,
                    say=say,
                    client=client
                )
            else:
                # Handle text-only queries (product search)
                await self._handle_text_query(
                    event=event,
                    text=text,
                    channel=channel,
                    user=user,
                    say=say,
                    client=client
                )
                
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)
            try:
                await say(f"❌ Error procesando tu solicitud: {str(e)[:200]}")
            except:
                pass
        finally:
            # Remove from processing set after a delay
            asyncio.create_task(self._cleanup_message(message_ts))
    
    async def _cleanup_message(self, message_ts: str):
        """Remove message from processing set after delay"""
        await asyncio.sleep(60)  # Keep in set for 60 seconds
        self.processing_messages.discard(message_ts)
    
    def _find_image_file(self, files: list) -> Optional[dict]:
        """Find first image file in list of files"""
        for f in files:
            mimetype = f.get("mimetype", "")
            if mimetype.startswith("image/"):
                return f
        return None
    
    async def _handle_image_analysis(
        self,
        event: dict,
        image_file: dict,
        text: str,
        channel: str,
        user: str,
        say,
        client: AsyncWebClient
    ):
        """
        Handle shelf image analysis request.
        Follows the exact flow:
        1. Add "eyes" reaction
        2. Download and analyze image
        3. Search products in Qdrant (semantic search)
        4. Generate comparison report
        5. Remove "eyes", add "white_check_mark"
        6. Send results
        """
        message_ts = event.get("ts")
        
        # Extract store ID from message text
        tienda_id = self._extract_tienda_id(text)
        
        if not tienda_id:
            output = (
                "⚠️ *Por favor incluye el número de tienda en tu mensaje.*\n\n"
                "Ejemplos:\n"
                "• `Tienda 810`\n"
                "• `tienda: 810`\n"
                "• `#810`\n"
                "• O simplemente el número `810` junto con la imagen"
            )
            await say(output)
            return
        
        # Step 1: Add "eyes" reaction to show we're processing
        await self._add_reaction(client, channel, message_ts, "eyes")
        
        try:
            # Send initial acknowledgment
            await say(f"🔍 Analizando imagen para *Tienda {tienda_id}*... Por favor espera.")
            
            # Step 2: Download image from Slack
            image_url = image_file.get("url_private")
            if not image_url:
                raise ValueError("No se pudo obtener URL de la imagen")
            
            logger.info(f"📥 Downloading image from Slack...")
            image_bytes = await self.vision.download_image_from_slack(
                image_url, 
                settings.SLACK_BOT_TOKEN
            )
            
            # Step 3: Analyze image with Gemini Vision
            logger.info(f"🔬 Analyzing image with Gemini...")
            productos, tokens_used = await self.vision.analyze_shelf_image_with_tokens(image_bytes)
            
            if not productos:
                await self._remove_reaction(client, channel, message_ts, "eyes")
                await self._add_reaction(client, channel, message_ts, "warning")
                await say(
                    "⚠️ No se pudieron identificar productos en la imagen.\n"
                    "Asegúrate de que la imagen muestre claramente los productos y precios."
                )
                return
            
            # Send progress update
            await say(f"📦 Se identificaron *{len(productos)}* productos. Validando precios...")
            
            # Step 4: Validate prices against Qdrant database
            logger.info(f"💰 Validating prices for {len(productos)} products...")
            validaciones = await self.validator.validate_products(productos, tienda_id)
            
            # Step 5: Remove "eyes" and add "white_check_mark"
            await self._remove_reaction(client, channel, message_ts, "eyes")
            await self._add_reaction(client, channel, message_ts, "white_check_mark")
            
            # Step 6: Format and send results
            resultado = self.validator.format_results_for_slack(validaciones, tienda_id)
            
            # Split message if too long (Slack limit is ~4000 chars)
            if len(resultado) > 3900:
                parts = self._split_message(resultado)
                for part in parts:
                    await say(part)
            else:
                await say(resultado)
            
            logger.info(f"✅ Image analysis complete for store {tienda_id}")
            
        except Exception as e:
            logger.error(f"❌ Image analysis failed: {e}", exc_info=True)
            await self._remove_reaction(client, channel, message_ts, "eyes")
            await self._add_reaction(client, channel, message_ts, "x")
            await say(f"❌ Error al analizar la imagen: {str(e)[:200]}")
    
    async def _handle_text_query(
        self,
        event: dict,
        text: str,
        channel: str,
        user: str,
        say,
        client: AsyncWebClient
    ):
        """
        Handle text-based product queries.
        Uses Qdrant semantic search for fuzzy matching.
        """
        message_ts = event.get("ts")
        
        # Check if it's a search query
        if not text or len(text.strip()) < 3:
            return
        
        # FIRST: Check if it's a greeting or help request
        if self._is_greeting_or_help(text):
            await self._add_reaction(client, channel, message_ts, "eyes")
            await say(self._get_help_message())
            await self._remove_reaction(client, channel, message_ts, "eyes")
            await self._add_reaction(client, channel, message_ts, "white_check_mark")
            return
        
        # Extract store ID
        tienda_id = self._extract_tienda_id(text)
        
        # Extract product search term
        search_term = self._extract_search_term(text)
        
        # If no valid search term, ignore
        if not search_term or len(search_term) < 3:
            return
        
        if not tienda_id:
            await self._add_reaction(client, channel, message_ts, "eyes")
            await say(
                "⚠️ Para buscar un producto necesito el número de tienda.\n"
                f"Ejemplo: `Tráeme el precio de {search_term} de la tienda 810`"
            )
            await self._remove_reaction(client, channel, message_ts, "eyes")
            await self._add_reaction(client, channel, message_ts, "x")
            return
        
        # Add eyes reaction to show we're processing
        await self._add_reaction(client, channel, message_ts, "eyes")
        
        try:
            # Search for products using Qdrant semantic search
            matches = await self.validator.qdrant.search_products(
                query=search_term.upper(),
                tienda_id=str(tienda_id),
                limit=20,
                score_threshold=0.5
            )
            
            # Remove eyes reaction
            await self._remove_reaction(client, channel, message_ts, "eyes")
            
            if matches:
                # Format results
                resultado = self._format_search_results(matches, search_term, tienda_id)
                await say(resultado)
                await self._add_reaction(client, channel, message_ts, "white_check_mark")
            else:
                await say(
                    f"⚠️ No encontré *\"{search_term}\"* en la tienda {tienda_id}.\n"
                    "Intenta con otro nombre o verifica el número de tienda."
                )
                await self._add_reaction(client, channel, message_ts, "x")
                
        except Exception as e:
            await self._remove_reaction(client, channel, message_ts, "eyes")
            await self._add_reaction(client, channel, message_ts, "x")
            logger.error(f"Search failed: {e}")
            await say(f"❌ Error en la búsqueda: {str(e)[:100]}")
    
    def _format_search_results(
        self, 
        matches: list, 
        search_term: str, 
        tienda_id: int
    ) -> str:
        """
        Format Qdrant search results for Slack.
        Shows product name, price, and similarity score.
        """
        if not matches:
            return f"⚠️ No encontré *\"{search_term}\"* en la tienda {tienda_id}."
        
        lines = [
            f"🔍 Resultados para *\"{search_term}\"* en tienda *{tienda_id}*:",
            "",
            "```",
            f"{'#':<4} {'PRODUCTO':<45} {'PRECIO':>10} {'SIMILITUD':>10}",
            "-" * 75
        ]
        
        for i, match in enumerate(matches, 1):
            nombre = match.nombre[:44] if len(match.nombre) > 44 else match.nombre
            precio = f"${match.precio:.2f}"
            score = f"{match.score:.0%}"
            lines.append(f"{i:<4} {nombre:<45} {precio:>10} {score:>10}")
        
        lines.append("```")
        lines.append(f"\n_Se encontraron {len(matches)} productos similares._")
        
        return "\n".join(lines)
    
    def _extract_tienda_id(self, text: str) -> Optional[int]:
        """
        Extract store ID from message text.
        Supports multiple formats.
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Patrones en orden de especificidad
        patterns = [
            r'tienda\s*[#:]?\s*(\d+)',      # "tienda 810", "tienda: 810", "tienda #810"
            r'store\s*[#:]?\s*(\d+)',        # "store 810"
            r'sucursal\s*[#:]?\s*(\d+)',     # "sucursal 810"
            r'#(\d{3,4})\b',                 # "#810"
            r'\b(\d{3,4})\b'                 # Standalone 3-4 digit number as fallback
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                tienda_id = int(match.group(1))
                # Validar rango razonable (ajustar según tu negocio)
                if 1 <= tienda_id <= 9999:
                    return tienda_id
        
        return None
    
    def _extract_search_term(self, text: str) -> Optional[str]:
        """Extract product search term from message"""
        if not text:
            return None
        
        cleaned = text
        
        # Remover menciones del bot primero
        cleaned = re.sub(r'<@[A-Z0-9]+>', '', cleaned)
        
        # Remover referencias a tienda
        cleaned = re.sub(r'(de\s+la\s+)?tienda\s*[#:]?\s*\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(de\s+la\s+)?store\s*[#:]?\s*\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(de\s+la\s+)?sucursal\s*[#:]?\s*\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'#\d+', '', cleaned)
        
        # Remover frases comunes de solicitud (en orden de más específico a menos)
        frases_remover = [
            r'tr[aá]eme\s+el\s+precio\s+de\s+(la|el|los|las)?\s*',
            r'cu[aá]l\s+es\s+el\s+precio\s+de\s+(la|el|los|las)?\s*',
            r'dame\s+el\s+precio\s+de\s+(la|el|los|las)?\s*',
            r'quiero\s+(saber\s+)?(el\s+)?precio\s+de\s+(la|el|los|las)?\s*',
            r'consulta\s+(el\s+)?precio\s+de\s+(la|el|los|las)?\s*',
            r'busca(r)?\s+(el\s+)?precio\s+de\s+(la|el|los|las)?\s*',
            r'precio\s+de\s+(la|el|los|las)?\s*',
            r'tr[aá]eme\s+(el|la|los|las)?\s*',
            r'cu[aá]l\s+es\s+(el|la)?\s*',
            r'dame\s+(el|la|los|las)?\s*',
            r'busca(r)?\s*',
            r'precio\s+de(l)?\s*',
            r'\bprecio\b',
            r'\bcuanto\s+cuesta\b',
            r'\bcuánto\s+cuesta\b',
        ]
        
        for patron in frases_remover:
            cleaned = re.sub(patron, '', cleaned, flags=re.IGNORECASE)
        
        # Limpiar espacios múltiples y extremos
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Remover artículos sueltos al inicio
        cleaned = re.sub(r'^(el|la|los|las|de|del)\s+', '', cleaned, flags=re.IGNORECASE)
        
        cleaned = cleaned.strip()
        
        return cleaned if len(cleaned) > 2 else None
    
    def _is_greeting_or_help(self, text: str) -> bool:
        """
        Check if message is a greeting or help request.
        Returns False if the message contains a store ID (indicating a product query).
        """
        text_lower = text.lower()
        
        # If message contains a store ID, it's likely a product query, not a greeting
        if self._extract_tienda_id(text):
            return False
        
        # Pure greetings and help requests (no product/store context)
        greetings = [
            'hola', 'hello', 'hi', 'hey', 'buenos días', 'buenas tardes', 'buenas noches',
            'ayuda', 'help', 'qué puedes', 'que puedes', 'para qué sirves', 
            'para que sirves', 'qué haces', 'que haces', 'cómo funciona', 'como funciona'
        ]
        
        # Only match if it's a short message or contains greeting words without product context
        is_greeting = any(g in text_lower for g in greetings)
        
        # If it's just "?" alone, it's help
        if text.strip() == '?':
            return True
        
        return is_greeting
    
    def _get_help_message(self) -> str:
        """Return the help/greeting message"""
        return (
            "¡Hola! 👋 Soy *Patricia*, tu asistente de análisis de precios. ¿Qué puedo hacer por ti?\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔍 *BÚSQUEDA EN BASE DE DATOS*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Puedo buscar productos en nuestra base de datos interna para verificar que los precios en tienda sean los correctos.\n\n"
            "*Ejemplo:*\n"
            "• _\"¿Cuánto cuesta la Harina en la tienda 100?\"_\n"
            "• _\"Busca el precio del Queso Panela en tienda 205\"_\n\n"
            "⚠️ *Importante:* Siempre indica el número de tienda, ya que cada una tiene sus propios precios.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📸 *ANÁLISIS POR IMAGEN*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "También puedo analizar precios desde fotos de los estantes de tu tienda.\n\n"
            "*Ejemplo:*\n"
            "• _\"Por favor analiza los productos de esta imagen de la tienda 100\"_\n"
            "• _\"Revisa los precios de esta foto de la tienda 305\"_\n\n"
            "*Mi análisis incluye:*\n"
            "• Identificación de productos y precios\n"
            "• Comparación con base de datos\n"
            "• Estado del producto (correcto/incorrecto)\n"
            "• Diferencia de precios si aplica\n"
            "• Tienda de referencia\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "¿En qué puedo ayudarte hoy? 😊"
        )
    
    def _split_message(self, message: str, max_length: int = 3900) -> list:
        """Split long message into chunks for Slack"""
        if len(message) <= max_length:
            return [message]
        
        parts = []
        current = ""
        
        for line in message.split('\n'):
            if len(current) + len(line) + 1 > max_length:
                parts.append(current)
                current = line
            else:
                current = current + '\n' + line if current else line
        
        if current:
            parts.append(current)
        
        return parts
    
    async def _add_reaction(
        self, 
        client: AsyncWebClient, 
        channel: str, 
        timestamp: str, 
        reaction: str
    ):
        """Add reaction to a message (silently fail)"""
        try:
            await client.reactions_add(
                channel=channel,
                timestamp=timestamp,
                name=reaction
            )
        except Exception as e:
            logger.debug(f"Could not add reaction {reaction}: {e}")
    
    async def _remove_reaction(
        self, 
        client: AsyncWebClient, 
        channel: str, 
        timestamp: str, 
        reaction: str
    ):
        """Remove reaction from a message (silently fail)"""
        try:
            await client.reactions_remove(
                channel=channel,
                timestamp=timestamp,
                name=reaction
            )
        except Exception as e:
            logger.debug(f"Could not remove reaction {reaction}: {e}")
