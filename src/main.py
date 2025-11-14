#!/usr/bin/env python3
"""
ADS-B Data Ingestion Service - Main Entry Point
"""

import sys
import os
import signal
import logging
import time
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config_manager import ConfigManager
from database_manager import DatabaseManager
from dump1090_client import Dump1090Client
from adsb_parser import ADSBParser
from data_processor import DataProcessor

# Service state
running = True
service = None


def setup_logging(log_config: dict):
    """Setup logging configuration"""
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    log_file = log_config.get('file', '/var/log/adsb-ingestion/service.log')
    max_bytes = log_config.get('max_bytes', 10485760)  # 10MB
    backup_count = log_config.get('backup_count', 5)
    
    # Create log directory if needed
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not setup file logging: {e}")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    running = False


def is_running():
    """Check if service should continue running"""
    return running


class ADSBIngestionService:
    """Main service class"""
    
    def __init__(self, config_path: str = None):
        """Initialize the service"""
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self.config = ConfigManager(config_path)
        
        # Initialize components
        self.db = DatabaseManager(self.config.get_database_config())
        self.client = Dump1090Client(
            **self.config.get_dump1090_config()
        )
        self.parser = ADSBParser()
        self.processor = DataProcessor(
            self.db,
            self.config.get_processing_config()
        )
        
        # Statistics thread
        self.stats_thread = None
        
    def message_callback(self, line: str):
        """Handle incoming message line"""
        parsed = self.parser.parse(line)
        if parsed:
            self.processor.add_message(parsed)
    
    def print_stats(self):
        """Periodically print statistics"""
        while is_running():
            time.sleep(60)  # Print every minute
            
            proc_stats = self.processor.get_stats()
            db_stats = self.db.get_stats()
            
            self.logger.info("=== Service Statistics ===")
            self.logger.info(f"Messages Received: {proc_stats['messages_received']}")
            self.logger.info(f"Messages Processed: {proc_stats['messages_processed']}")
            self.logger.info(f"Messages Discarded: {proc_stats['messages_discarded']}")
            self.logger.info(f"Batches Written: {proc_stats['batches_written']}")
            self.logger.info(f"Queue Size: {proc_stats['queue_size']}")
            self.logger.info(f"Errors: {proc_stats['errors']}")
            self.logger.info(f"Total Aircraft: {db_stats.get('total_aircraft', 0)}")
            self.logger.info(f"Total Messages: {db_stats.get('total_messages', 0)}")
            self.logger.info(f"Messages Last Hour: {db_stats.get('messages_last_hour', 0)}")
    
    def run(self):
        """Run the service"""
        self.logger.info("Starting ADS-B Ingestion Service")
        
        # Start periodic flush thread
        flush_thread = threading.Thread(
            target=self.processor.periodic_flush,
            args=(is_running,),
            daemon=True
        )
        flush_thread.start()
        
        # Start statistics thread
        self.stats_thread = threading.Thread(
            target=self.print_stats,
            daemon=True
        )
        self.stats_thread.start()
        
        # Main message reading loop
        try:
            self.client.read_messages(self.message_callback, is_running)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Cleanup and shutdown"""
        self.logger.info("Shutting down service...")
        
        # Flush remaining messages
        self.processor.force_flush()
        
        # Disconnect client
        self.client.disconnect()
        
        # Print final stats
        proc_stats = self.processor.get_stats()
        self.logger.info(f"Final stats - Received: {proc_stats['messages_received']}, "
                        f"Processed: {proc_stats['messages_processed']}")
        
        self.logger.info("Service stopped")


def main():
    """Main entry point"""
    global service
    
    # Parse command line arguments
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        # Check default locations
        default_paths = [
            '/etc/adsb-ingestion/config.yaml',
            './config/config.yaml',
            './config.yaml'
        ]
        for path in default_paths:
            if os.path.exists(path):
                config_path = path
                break
    
    # Load config for logging setup
    try:
        config = ConfigManager(config_path)
        setup_logging(config.get_logging_config())
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("ADS-B Data Ingestion Service v1.0.0")
    logger.info("=" * 60)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run service
    try:
        service = ADSBIngestionService(config_path)
        service.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
    