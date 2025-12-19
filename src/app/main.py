"""
A-Patricia Agent - Price Validation Service
Main entry point for the application.

This service replaces the n8n workflow "AgentePatricia" with a more
efficient Python implementation that:
- Uses a single Gemini call for image analysis (instead of multiple LLM calls)
- Uses Qdrant vector database for semantic product matching
- Supports high concurrency through async processing
- Runs in an isolated Docker container
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Response
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from app.config import settings
from app.services.vision import VisionService
from app.services.qdrant_service import QdrantService
from app.services.price_validator import PriceValidator
from app.services.slack_handler import SlackHandler

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Service instances (initialized on startup)
vision_service: Optional[VisionService] = None
qdrant_service: Optional[QdrantService] = None
price_validator: Optional[PriceValidator] = None
slack_handler: Optional[SlackHandler] = None

# Slack Bolt App - handles all Slack events
slack_app = AsyncApp(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Initializes all services on startup and cleans up on shutdown.
    """
    global vision_service, qdrant_service, price_validator, slack_handler
    
    logger.info("=" * 60)
    logger.info("🚀 Starting A-Patricia Agent...")
    logger.info("=" * 60)
    
    try:
        # Initialize services
        logger.info("Initializing Vision Service (Gemini)...")
        vision_service = VisionService()
        
        logger.info("Initializing Qdrant Service (Vector Database)...")
        qdrant_service = QdrantService()
        
        logger.info("Initializing Price Validator...")
        price_validator = PriceValidator(qdrant_service)
        
        logger.info("Initializing Slack Handler...")
        slack_handler = SlackHandler(
            slack_app=slack_app,
            vision_service=vision_service,
            price_validator=price_validator
        )
        
        # Register Slack event handlers
        slack_handler.register_handlers()
        
        # Log Qdrant stats
        stats = await qdrant_service.get_collection_stats()
        logger.info(f"   Qdrant: {stats['total_points']} products indexed")
        
        logger.info("=" * 60)
        logger.info("✅ A-Patricia Agent ready!")
        logger.info(f"   Mode: {'Socket Mode' if settings.SLACK_SOCKET_MODE else 'HTTP Mode'}")
        logger.info(f"   Port: {settings.PORT}")
        logger.info("=" * 60)
        
        # If using Socket Mode, start it
        if settings.SLACK_SOCKET_MODE and settings.SLACK_APP_TOKEN:
            asyncio.create_task(start_socket_mode())
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}", exc_info=True)
        raise
    
    logger.info("👋 Shutting down A-Patricia Agent...")


async def start_socket_mode():
    """
    Start Slack Socket Mode for real-time event handling.
    Socket Mode is preferred for bots as it doesn't require a public URL.
    """
    try:
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        
        logger.info("🔌 Starting Slack Socket Mode...")
        socket_handler = AsyncSocketModeHandler(slack_app, settings.SLACK_APP_TOKEN)
        await socket_handler.start_async()
    except Exception as e:
        logger.error(f"❌ Socket Mode failed: {e}", exc_info=True)


# FastAPI App
app = FastAPI(
    title="A-Patricia Agent",
    description="Price validation agent for retail stores. Analyzes shelf images and compares prices against database.",
    version="1.0.0",
    lifespan=lifespan
)

# Slack HTTP request handler (for non-socket mode)
slack_request_handler = AsyncSlackRequestHandler(slack_app)


@app.get("/health")
async def health_check():
    """
    Health check endpoint for Docker/Traefik health checks.
    Returns service status and basic info.
    """
    return {
        "status": "healthy",
        "service": "a-patricia",
        "version": "1.0.0",
        "mode": "socket" if settings.SLACK_SOCKET_MODE else "http"
    }


@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "name": "A-Patricia Price Validation Agent",
        "description": "Validates shelf prices against database",
        "status": "running",
        "endpoints": {
            "/health": "Health check",
            "/slack/events": "Slack events (HTTP mode only)"
        }
    }


@app.post("/slack/events")
async def slack_events(request: Request):
    """
    Handle Slack events via HTTP.
    Only used when Socket Mode is disabled.
    Slack sends events here for URL verification and event callbacks.
    """
    return await slack_request_handler.handle(request)


@app.post("/slack/interactions")
async def slack_interactions(request: Request):
    """Handle Slack interactive components (buttons, modals, etc.)"""
    return await slack_request_handler.handle(request)


# Entry point for running directly
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False
    )
