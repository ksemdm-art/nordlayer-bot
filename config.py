import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Telegram Bot Configuration
    telegram_bot_token: str = ""
    webhook_url: str = ""
    
    # API Configuration
    api_base_url: str = "http://localhost:8000"
    api_timeout: int = 30
    
    # Admin Configuration
    admin_chat_ids: str = ""  # Comma-separated list of admin chat IDs
    
    # Logging Configuration
    log_level: str = "INFO"
    log_file: str = "logs/bot.log"
    log_max_bytes: int = 10 * 1024 * 1024  # 10MB
    log_backup_count: int = 5
    
    # Session Configuration
    session_cleanup_hours: int = 24
    
    # Health Check Configuration
    health_check_port: int = 8080
    
    # Webhook Configuration
    webhook_port: int = 8081
    webhook_host: str = "0.0.0.0"
    
    # Production Configuration
    environment: str = "development"  # development, staging, production
    debug: bool = False
    
    # Graceful shutdown timeout
    shutdown_timeout: int = 30
    
    # File upload limits
    max_file_size_mb: int = 50
    allowed_file_extensions: str = ".stl,.obj,.3mf"
    
    class Config:
        env_file = ".env"
    
    @property
    def admin_chat_ids_list(self) -> List[int]:
        """Convert comma-separated admin IDs to list of integers"""
        if not self.admin_chat_ids:
            return []
        try:
            return [int(chat_id.strip()) for chat_id in self.admin_chat_ids.split(",") if chat_id.strip()]
        except ValueError:
            return []
    
    @property
    def allowed_extensions_list(self) -> List[str]:
        """Convert comma-separated extensions to list"""
        return [ext.strip() for ext in self.allowed_file_extensions.split(",") if ext.strip()]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"

settings = Settings()