"""
Structured logging configuration for Telegram bot.
"""
import logging
import logging.config
import json
import sys
from datetime import datetime
from pathlib import Path

class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "service": "telegram_bot"
        }
        
        # Add extra fields if present
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'chat_id'):
            log_entry['chat_id'] = record.chat_id
        if hasattr(record, 'message_type'):
            log_entry['message_type'] = record.message_type
        if hasattr(record, 'handler'):
            log_entry['handler'] = record.handler
        if hasattr(record, 'processing_time_ms'):
            log_entry['processing_time_ms'] = record.processing_time_ms
        if hasattr(record, 'order_id'):
            log_entry['order_id'] = record.order_id
        if hasattr(record, 'service_id'):
            log_entry['service_id'] = record.service_id
        if hasattr(record, 'error_type'):
            log_entry['error_type'] = record.error_type
        if hasattr(record, 'endpoint'):
            log_entry['endpoint'] = record.endpoint
        if hasattr(record, 'status_code'):
            log_entry['status_code'] = record.status_code
        if hasattr(record, 'duration_ms'):
            log_entry['duration_ms'] = record.duration_ms
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)

def setup_structured_logging(service_name: str = "telegram_bot", 
                           log_level: str = "INFO", 
                           log_file: str = None) -> logging.Logger:
    """Setup structured logging configuration for the bot."""
    
    # Create logs directory if log file is specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": StructuredFormatter,
            },
            "simple": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "structured",
                "stream": sys.stdout
            }
        },
        "loggers": {
            service_name: {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "telegram": {
                "level": "WARNING",  # Reduce telegram library noise
                "handlers": ["console"],
                "propagate": False
            },
            "httpx": {
                "level": "WARNING",  # Reduce HTTP client noise
                "handlers": ["console"],
                "propagate": False
            },
            "aiohttp": {
                "level": "WARNING",  # Reduce HTTP client noise
                "handlers": ["console"],
                "propagate": False
            }
        },
        "root": {
            "level": log_level,
            "handlers": ["console"]
        }
    }
    
    # Add file handler if log file is specified
    if log_file:
        config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": "structured",
            "filename": log_file,
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }
        
        # Add file handler to all loggers
        for logger_config in config["loggers"].values():
            logger_config["handlers"].append("file")
        config["root"]["handlers"].append("file")
    
    logging.config.dictConfig(config)
    
    # Return the main service logger
    return logging.getLogger(service_name)

class BotLogContext:
    """Context manager for adding bot-specific logging context."""
    
    def __init__(self, logger: logging.Logger, **context):
        self.logger = logger
        self.context = context
        self.old_context = {}
    
    def __enter__(self):
        # Store old context and set new context
        for key, value in self.context.items():
            if hasattr(self.logger, key):
                self.old_context[key] = getattr(self.logger, key)
            setattr(self.logger, key, value)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore old context
        for key in self.context.keys():
            if key in self.old_context:
                setattr(self.logger, key, self.old_context[key])
            else:
                delattr(self.logger, key)

def log_user_interaction(logger: logging.Logger, user_id: int, chat_id: int, 
                        message_type: str, handler: str, processing_time: float = None):
    """Log user interaction with structured data."""
    extra = {
        'user_id': user_id,
        'chat_id': chat_id,
        'message_type': message_type,
        'handler': handler
    }
    
    if processing_time is not None:
        extra['processing_time_ms'] = processing_time * 1000
    
    logger.info(f"User interaction: {message_type} handled by {handler}", extra=extra)

def log_order_event(logger: logging.Logger, user_id: int, order_id: str, 
                   event: str, service_id: int = None, details: dict = None):
    """Log order-related events."""
    extra = {
        'user_id': user_id,
        'order_id': order_id,
        'event': event
    }
    
    if service_id:
        extra['service_id'] = service_id
    
    if details:
        extra.update(details)
    
    logger.info(f"Order event: {event} for order {order_id}", extra=extra)

def log_api_call(logger: logging.Logger, endpoint: str, method: str, 
                status_code: int, duration: float, user_id: int = None):
    """Log API call with structured data."""
    extra = {
        'endpoint': endpoint,
        'method': method,
        'status_code': status_code,
        'duration_ms': duration * 1000
    }
    
    if user_id:
        extra['user_id'] = user_id
    
    level = logging.INFO
    if status_code >= 500:
        level = logging.ERROR
    elif status_code >= 400:
        level = logging.WARNING
    
    logger.log(level, f"API call: {method} {endpoint} - {status_code}", extra=extra)

def log_bot_error(logger: logging.Logger, error: Exception, context: dict = None):
    """Log bot error with structured context."""
    extra = {
        'error_type': type(error).__name__
    }
    
    if context:
        extra.update(context)
    
    logger.error(f"Bot error: {str(error)}", extra=extra, exc_info=True)