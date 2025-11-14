"""
Configuration Manager
Handles loading and validating configuration from YAML and environment variables
"""

import os
import yaml
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration with environment variable overrides"""
    
    DEFAULT_CONFIG = {
        'dump1090': {
            'host': 'localhost',
            'port': 30003,
            'reconnect_interval': 5,
            'max_reconnect_interval': 60
        },
        'database': {
            'host': 'localhost',
            'port': 3306,
            'database': 'adsb',
            'user': 'adsb_user',
            'password': '',
            'pool_size': 5,
            'pool_name': 'adsb_pool'
        },
        'processing': {
            'batch_size': 100,
            'batch_timeout': 1.0,
            'enable_deduplication': True,
            'dedup_window': 2
        },
        'logging': {
            'level': 'INFO',
            'file': '/var/log/adsb-ingestion/service.log',
            'max_bytes': 10485760,
            'backup_count': 5
        }
    }
    
    def __init__(self, config_path: str = None):
        """
        Initialize configuration manager
        
        Args:
            config_path: Path to YAML configuration file
        """
        self.config = self._load_config(config_path)
        self._apply_env_overrides()
        self._validate_config()
        
    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        config = self.DEFAULT_CONFIG.copy()
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = yaml.safe_load(f)
                    if user_config:
                        config = self._deep_merge(config, user_config)
                logger.info(f"Loaded configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}. Using defaults.")
        else:
            logger.info("No config file provided, using defaults")
            
        return config
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge override dict into base dict"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides"""
        # Dump1090 settings
        if os.getenv('DUMP1090_HOST'):
            self.config['dump1090']['host'] = os.getenv('DUMP1090_HOST')
        if os.getenv('DUMP1090_PORT'):
            self.config['dump1090']['port'] = int(os.getenv('DUMP1090_PORT'))
        
        # Database settings
        if os.getenv('DB_HOST'):
            self.config['database']['host'] = os.getenv('DB_HOST')
        if os.getenv('DB_PORT'):
            self.config['database']['port'] = int(os.getenv('DB_PORT'))
        if os.getenv('DB_NAME'):
            self.config['database']['database'] = os.getenv('DB_NAME')
        if os.getenv('DB_USER'):
            self.config['database']['user'] = os.getenv('DB_USER')
        if os.getenv('DB_PASSWORD'):
            self.config['database']['password'] = os.getenv('DB_PASSWORD')
        
        # Logging
        if os.getenv('LOG_LEVEL'):
            self.config['logging']['level'] = os.getenv('LOG_LEVEL')
        if os.getenv('LOG_FILE'):
            self.config['logging']['file'] = os.getenv('LOG_FILE')
    
    def _validate_config(self):
        """Validate required configuration parameters"""
        required_fields = [
            ('dump1090', 'host'),
            ('dump1090', 'port'),
            ('database', 'host'),
            ('database', 'database'),
            ('database', 'user')
        ]
        
        for section, field in required_fields:
            if not self.config.get(section, {}).get(field):
                raise ValueError(f"Missing required configuration: {section}.{field}")
        
        # Validate database password is set
        if not self.config['database']['password']:
            logger.warning("Database password is empty! This is insecure.")
    
    def get(self, *keys, default=None):
        """Get nested configuration value"""
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value
    
    def get_dump1090_config(self) -> Dict[str, Any]:
        """Get Dump1090 configuration"""
        return self.config['dump1090']
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        return self.config['database']
    
    def get_processing_config(self) -> Dict[str, Any]:
        """Get processing configuration"""
        return self.config['processing']
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration"""
        return self.config['logging']
        