"""
Web Admin Backend - FastAPI Application
Provides REST API for file management and product indexing.
"""
import logging
import sys
from datetime import timedelta
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os

from app.config import settings
from app.security import (
    create_access_token, verify_token, hash_password, verify_password,
    encrypt_data, decrypt_data, generate_file_id
)
from app.services.minio_service import MinIOService
from app.services.file_processor import FileProcessor
from app.services.qdrant_service import QdrantAdminService

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

# Services (initialized on startup)
minio_service: Optional[MinIOService] = None
file_processor: Optional[FileProcessor] = None
qdrant_service: Optional[QdrantAdminService] = None

# In-memory file registry (in production, use a database)
file_registry = {}


# Pydantic models
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class FileInfo(BaseModel):
    file_id: str
    filename: str
    size: int
    content_type: str
    products_count: int
    uploaded_at: str
    status: str


class FileListResponse(BaseModel):
    files: List[FileInfo]
    total: int


class StatsResponse(BaseModel):
    total_products: int
    total_files: int
    status: str


class ProductPreview(BaseModel):
    nombre: str
    precio: float
    tienda_id: Optional[str] = None
    codigo: Optional[str] = None
    categoria: Optional[str] = None


class EncryptedResponse(BaseModel):
    data: str  # Encrypted data


# Auth dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return user"""
    token = credentials.credentials
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle"""
    global minio_service, file_processor, qdrant_service
    
    logger.info("🚀 Starting Web Admin Backend...")
    
    try:
        logger.info("Initializing MinIO Service...")
        minio_service = MinIOService()
        
        logger.info("Initializing File Processor...")
        file_processor = FileProcessor()
        
        logger.info("Initializing Qdrant Service...")
        qdrant_service = QdrantAdminService()
        
        # Load existing file registry from Qdrant
        await _load_file_registry()
        
        logger.info("✅ Web Admin Backend ready!")
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize: {e}", exc_info=True)
        raise
    
    logger.info("👋 Shutting down Web Admin Backend...")


async def _load_file_registry():
    """Load file registry from Qdrant on startup"""
    global file_registry
    
    try:
        file_ids = await qdrant_service.get_unique_file_ids()
        for file_id in file_ids:
            count = await qdrant_service.count_by_file(file_id)
            # Basic info - in production, store in database
            file_registry[file_id] = {
                "file_id": file_id,
                "filename": f"{file_id}.data",
                "size": 0,
                "content_type": "application/octet-stream",
                "products_count": count,
                "uploaded_at": "unknown",
                "status": "indexed"
            }
        logger.info(f"Loaded {len(file_registry)} files from registry")
    except Exception as e:
        logger.warning(f"Could not load file registry: {e}")


# FastAPI app
app = FastAPI(
    title="A-Patricia Web Admin",
    description="File management and product indexing for A-Patricia",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Health & Public Endpoints
# ============================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "web-admin"}


# ============================================
# Authentication Endpoints
# ============================================

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token"""
    # Verify credentials
    if request.username != settings.ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if request.password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create token
    expires = timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    token = create_access_token(
        data={"sub": request.username, "role": "admin"},
        expires_delta=expires
    )
    
    return TokenResponse(
        access_token=token,
        expires_in=settings.JWT_EXPIRATION_HOURS * 3600
    )


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info"""
    return {"username": user.get("sub"), "role": user.get("role")}


# ============================================
# File Management Endpoints
# ============================================

@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    tienda_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    """
    Upload a file and index products into Qdrant.
    Supports CSV, Excel, PDF, TXT, DOCX, Images.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Read file
    file_data = await file.read()
    if len(file_data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    # Generate file ID
    file_id = generate_file_id()
    
    try:
        # Process file to extract products
        logger.info(f"Processing file: {file.filename}")
        products, metadata = await file_processor.process_file(
            file_data,
            file.filename,
            file.content_type or "application/octet-stream"
        )
        
        # Add tienda_id to all products if provided
        if tienda_id:
            for product in products:
                if not product.get("tienda_id"):
                    product["tienda_id"] = tienda_id
        
        # Upload original file to MinIO
        await minio_service.upload_file(
            file_id=file_id,
            file_data=file_data,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream"
        )
        
        # Index products in Qdrant
        index_result = await qdrant_service.index_products(products, file_id)
        
        # Store in registry
        from datetime import datetime
        file_info = {
            "file_id": file_id,
            "filename": file.filename,
            "size": len(file_data),
            "content_type": file.content_type or "application/octet-stream",
            "products_count": index_result["indexed"],
            "uploaded_at": datetime.utcnow().isoformat(),
            "status": "indexed",
            "metadata": metadata
        }
        file_registry[file_id] = file_info
        
        # Encrypt response data
        response_data = {
            "file_id": file_id,
            "filename": file.filename,
            "products_extracted": len(products),
            "products_indexed": index_result["indexed"],
            "errors": index_result["errors"],
            "metadata": metadata
        }
        
        return EncryptedResponse(data=encrypt_data(response_data))
        
    except Exception as e:
        logger.error(f"Error processing file: {e}", exc_info=True)
        # Cleanup on error
        await minio_service.delete_folder(file_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/files", response_model=EncryptedResponse)
async def list_files(user: dict = Depends(get_current_user)):
    """List all uploaded files"""
    files = list(file_registry.values())
    
    # Update product counts from Qdrant
    for f in files:
        count = await qdrant_service.count_by_file(f["file_id"])
        f["products_count"] = count
    
    response_data = {
        "files": files,
        "total": len(files)
    }
    
    return EncryptedResponse(data=encrypt_data(response_data))


@app.get("/api/files/{file_id}")
async def get_file_info(file_id: str, user: dict = Depends(get_current_user)):
    """Get file information"""
    if file_id not in file_registry:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_info = file_registry[file_id]
    
    # Update product count
    count = await qdrant_service.count_by_file(file_id)
    file_info["products_count"] = count
    
    return EncryptedResponse(data=encrypt_data(file_info))


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str, user: dict = Depends(get_current_user)):
    """Delete a file and its indexed products"""
    if file_id not in file_registry:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_info = file_registry[file_id]
    
    try:
        # Delete from Qdrant
        deleted_products = await qdrant_service.delete_by_file(file_id)
        
        # Delete from MinIO
        await minio_service.delete_folder(file_id)
        
        # Remove from registry
        del file_registry[file_id]
        
        response_data = {
            "file_id": file_id,
            "filename": file_info["filename"],
            "products_deleted": deleted_products,
            "status": "deleted"
        }
        
        return EncryptedResponse(data=encrypt_data(response_data))
        
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/files/{file_id}/preview")
async def get_file_preview(
    file_id: str,
    limit: int = Query(default=100, le=500),
    user: dict = Depends(get_current_user)
):
    """Get preview of indexed products from a file"""
    if file_id not in file_registry:
        raise HTTPException(status_code=404, detail="File not found")
    
    products = await qdrant_service.get_products_by_file(file_id, limit)
    
    response_data = {
        "file_id": file_id,
        "products": products,
        "count": len(products),
        "total": await qdrant_service.count_by_file(file_id)
    }
    
    return EncryptedResponse(data=encrypt_data(response_data))


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: str, user: dict = Depends(get_current_user)):
    """Get presigned URL to download original file"""
    if file_id not in file_registry:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_info = file_registry[file_id]
    
    try:
        url = await minio_service.get_presigned_url(
            file_id,
            file_info["filename"],
            expires=3600
        )
        
        response_data = {
            "download_url": url,
            "filename": file_info["filename"],
            "expires_in": 3600
        }
        
        return EncryptedResponse(data=encrypt_data(response_data))
        
    except Exception as e:
        logger.error(f"Error generating download URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Stats Endpoints
# ============================================

@app.get("/api/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """Get system statistics"""
    qdrant_stats = await qdrant_service.get_stats()
    
    response_data = {
        "total_products": qdrant_stats["total_products"],
        "total_files": len(file_registry),
        "qdrant_status": qdrant_stats["status"]
    }
    
    return EncryptedResponse(data=encrypt_data(response_data))


# ============================================
# Decryption Endpoint (for frontend)
# ============================================

@app.post("/api/decrypt")
async def decrypt_response(
    encrypted: EncryptedResponse,
    user: dict = Depends(get_current_user)
):
    """Decrypt an encrypted response (for testing)"""
    try:
        decrypted = decrypt_data(encrypted.data)
        return decrypted
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid encrypted data")


# ============================================
# Static Files (React Frontend)
# ============================================

# Serve static files from the built React app
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

if os.path.exists(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes"""
        # Don't serve for API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Try to serve the requested file
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # Fall back to index.html for SPA routing
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        
        raise HTTPException(status_code=404, detail="Not found")


# Entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=3000,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False
    )
