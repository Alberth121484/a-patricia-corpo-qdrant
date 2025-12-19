"""
Configuration management for A-Patricia Agent
"""
import os
import json
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "A-Patricia"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8080
    
    # Slack Configuration
    SLACK_BOT_TOKEN: str
    SLACK_APP_TOKEN: Optional[str] = None
    SLACK_SIGNING_SECRET: str
    SLACK_SOCKET_MODE: bool = True
    
    # Google/Gemini Configuration
    GOOGLE_APPLICATION_CREDENTIALS_JSON: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # Qdrant Configuration (Vector Database)
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "products"
    
    # Processing Configuration
    PRICE_TOLERANCE_PERCENT: float = 5.0
    MAX_PRODUCTS_PER_IMAGE: int = 100
    SEARCH_LIMIT: int = 5
    SIMILARITY_THRESHOLD: float = 0.7
    
    # Allowed Slack User IDs (empty = all users allowed)
    ALLOWED_USER_IDS: str = ""
    
    class Config:
        env_file = ".env"
        extra = "ignore"
    
    def get_gcp_credentials(self) -> Optional[dict]:
        """Parse GCP credentials from JSON string"""
        if self.GOOGLE_APPLICATION_CREDENTIALS_JSON:
            try:
                creds = json.loads(self.GOOGLE_APPLICATION_CREDENTIALS_JSON)
                print(f"✅ GCP credentials loaded for project: {creds.get('project_id', 'unknown')}")
                return creds
            except json.JSONDecodeError as e:
                print(f"❌ Error parsing GOOGLE_APPLICATION_CREDENTIALS_JSON: Invalid JSON format")
                return None
        print("⚠️ GOOGLE_APPLICATION_CREDENTIALS_JSON not set")
        return None
    
    def get_allowed_users(self) -> list:
        """Get list of allowed Slack user IDs"""
        if not self.ALLOWED_USER_IDS:
            return []
        return [uid.strip() for uid in self.ALLOWED_USER_IDS.split(",") if uid.strip()]


settings = Settings()
