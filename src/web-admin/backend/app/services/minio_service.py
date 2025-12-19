"""
MinIO service for file storage
"""
import logging
from typing import BinaryIO, List, Optional
from datetime import timedelta
import io

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


class MinIOService:
    """Service for file storage in MinIO"""
    
    def __init__(self):
        """Initialize MinIO client"""
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()
        logger.info(f"✅ MinIOService initialized (bucket={self.bucket})")
    
    def _ensure_bucket(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Created bucket: {self.bucket}")
        except S3Error as e:
            logger.error(f"Error creating bucket: {e}")
            raise
    
    async def upload_file(
        self,
        file_id: str,
        file_data: bytes,
        filename: str,
        content_type: str
    ) -> dict:
        """
        Upload a file to MinIO.
        
        Args:
            file_id: Unique identifier for the file
            file_data: File content as bytes
            filename: Original filename
            content_type: MIME type
            
        Returns:
            Dict with file metadata
        """
        object_name = f"{file_id}/{filename}"
        
        try:
            # Upload file
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type
            )
            
            logger.info(f"Uploaded file: {object_name}")
            
            return {
                "file_id": file_id,
                "filename": filename,
                "object_name": object_name,
                "size": len(file_data),
                "content_type": content_type
            }
            
        except S3Error as e:
            logger.error(f"Error uploading file: {e}")
            raise
    
    async def download_file(self, file_id: str, filename: str) -> bytes:
        """
        Download a file from MinIO.
        
        Args:
            file_id: File identifier
            filename: Filename
            
        Returns:
            File content as bytes
        """
        object_name = f"{file_id}/{filename}"
        
        try:
            response = self.client.get_object(self.bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"Error downloading file: {e}")
            raise
    
    async def delete_file(self, file_id: str, filename: str) -> bool:
        """
        Delete a file from MinIO.
        
        Args:
            file_id: File identifier
            filename: Filename
            
        Returns:
            True if deleted successfully
        """
        object_name = f"{file_id}/{filename}"
        
        try:
            self.client.remove_object(self.bucket, object_name)
            logger.info(f"Deleted file: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error deleting file: {e}")
            return False
    
    async def delete_folder(self, file_id: str) -> int:
        """
        Delete all files with a given file_id prefix.
        
        Args:
            file_id: File identifier (folder prefix)
            
        Returns:
            Number of files deleted
        """
        try:
            objects = self.client.list_objects(self.bucket, prefix=f"{file_id}/")
            count = 0
            for obj in objects:
                self.client.remove_object(self.bucket, obj.object_name)
                count += 1
            logger.info(f"Deleted {count} files from folder: {file_id}")
            return count
        except S3Error as e:
            logger.error(f"Error deleting folder: {e}")
            return 0
    
    async def get_presigned_url(
        self, 
        file_id: str, 
        filename: str,
        expires: int = 3600
    ) -> str:
        """
        Get a presigned URL for file access.
        
        Args:
            file_id: File identifier
            filename: Filename
            expires: URL expiration in seconds
            
        Returns:
            Presigned URL string
        """
        object_name = f"{file_id}/{filename}"
        
        try:
            url = self.client.presigned_get_object(
                self.bucket,
                object_name,
                expires=timedelta(seconds=expires)
            )
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise
    
    async def list_files(self, prefix: str = "") -> List[dict]:
        """
        List all files in the bucket.
        
        Args:
            prefix: Optional prefix to filter files
            
        Returns:
            List of file metadata dicts
        """
        try:
            objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
            files = []
            for obj in objects:
                files.append({
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag
                })
            return files
        except S3Error as e:
            logger.error(f"Error listing files: {e}")
            return []
    
    async def file_exists(self, file_id: str, filename: str) -> bool:
        """Check if a file exists"""
        object_name = f"{file_id}/{filename}"
        try:
            self.client.stat_object(self.bucket, object_name)
            return True
        except S3Error:
            return False
