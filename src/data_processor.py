"""
Data Processor
Coordinates data flow, batching, and deduplication
"""

import logging
import time
import threading
from typing import List, Dict, Any
from collections import deque

logger = logging.getLogger(__name__)


class DataProcessor:
    """Processes and batches ADS-B messages for database insertion"""
    
    def __init__(self, database_manager, config: Dict[str, Any]):
        """
        Initialize data processor
        
        Args:
            database_manager: DatabaseManager instance
            config: Processing configuration
        """
        self.db = database_manager
        self.batch_size = config.get('batch_size', 100)
        self.batch_timeout = config.get('batch_timeout', 1.0)
        self.enable_deduplication = config.get('enable_deduplication', True)
        self.dedup_window = config.get('dedup_window', 2)
        
        self.message_queue = deque()
        self.lock = threading.Lock()
        self.last_flush = time.time()
        
        # Statistics
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'messages_discarded': 0,
            'batches_written': 0,
            'errors': 0
        }
        
        # Deduplication cache (simple time-based)
        self.recent_messages = deque(maxlen=1000)
        
    def add_message(self, message: Dict[str, Any]):
        """
        Add message to processing queue
        
        Args:
            message: Parsed message dictionary
        """
        with self.lock:
            self.stats['messages_received'] += 1
            
            # Deduplicate if enabled
            if self.enable_deduplication:
                if self._is_duplicate(message):
                    self.stats['messages_discarded'] += 1
                    return
            
            self.message_queue.append(message)
            self.recent_messages.append(self._message_key(message))
            
            # Check if we should flush
            if len(self.message_queue) >= self.batch_size:
                self._flush_batch()
            elif time.time() - self.last_flush >= self.batch_timeout:
                self._flush_batch()
    
    def _is_duplicate(self, message: Dict[str, Any]) -> bool:
        """Check if message is a recent duplicate"""
        key = self._message_key(message)
        return key in self.recent_messages
    
    def _message_key(self, message: Dict[str, Any]) -> str:
        """Generate unique key for message deduplication"""
        icao = message.get('icao24', '')
        timestamp = message.get('timestamp', '')
        msg_type = message.get('transmission_type', '')
        return f"{icao}:{timestamp}:{msg_type}"
    
    def _flush_batch(self):
        """Flush current batch to database"""
        if not self.message_queue:
            return
        
        messages = list(self.message_queue)
        self.message_queue.clear()
        
        try:
            inserted = self.db.batch_insert_messages(messages)
            self.stats['messages_processed'] += inserted
            self.stats['batches_written'] += 1
            self.last_flush = time.time()
            
            if inserted > 0:
                logger.debug(f"Flushed batch of {inserted} messages")
                
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}")
            self.stats['errors'] += 1
            # Re-queue messages for retry (optional)
            # self.message_queue.extendleft(reversed(messages))
    
    def force_flush(self):
        """Force flush any pending messages"""
        with self.lock:
            self._flush_batch()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        with self.lock:
            stats = self.stats.copy()
            stats['queue_size'] = len(self.message_queue)
            return stats
    
    def periodic_flush(self, running_flag):
        """Periodic flush thread"""
        while running_flag():
            time.sleep(0.1)  # Check every 100ms
            
            with self.lock:
                if time.time() - self.last_flush >= self.batch_timeout:
                    if self.message_queue:
                        self._flush_batch()
                        