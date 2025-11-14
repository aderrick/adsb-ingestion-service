"""
Database Manager
Handles MySQL connection pooling, queries, and batch inserts
"""

import logging
import time
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling, Error as MySQLError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages MySQL database connections and operations"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize database manager
        
        Args:
            config: Database configuration dictionary
        """
        self.config = config
        self.pool = None
        self._init_connection_pool()
    
    def _init_connection_pool(self):
        """Initialize MySQL connection pool"""
        try:
            self.pool = pooling.MySQLConnectionPool(
                pool_name=self.config.get('pool_name', 'adsb_pool'),
                pool_size=self.config.get('pool_size', 5),
                host=self.config['host'],
                port=self.config.get('port', 3306),
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                autocommit=False,
                charset='utf8mb4'
            )
            logger.info("Database connection pool initialized")
            self._verify_connection()
        except MySQLError as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    def _verify_connection(self):
        """Verify database connection and schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            logger.info(f"Connected to MySQL version: {version[0]}")
            
            # Verify tables exist
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = %s AND table_name IN ('aircraft', 'positions', 'messages')
            """, (self.config['database'],))
            
            table_count = cursor.fetchone()[0]
            if table_count < 3:
                logger.warning(f"Expected 3 tables, found {table_count}. Run schema.sql to initialize.")
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = self.pool.get_connection()
            yield conn
            conn.commit()
        except MySQLError as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
def batch_insert_messages(self, messages: List[Dict[str, Any]]) -> int:
    """
    Batch insert parsed ADS-B messages
    
    Args:
        messages: List of parsed message dictionaries
        
    Returns:
        Number of messages inserted
    """
    if not messages:
        return 0
    
    inserted = 0
    with self.get_connection() as conn:
        cursor = conn.cursor()
        
        try:
            # IMPORTANT: Insert aircraft FIRST to satisfy foreign key constraints
            self._upsert_aircraft(cursor, messages)
            
            # Now insert into messages table
            message_sql = """
                INSERT INTO messages 
                (icao24, message_type, timestamp, callsign, altitude, ground_speed, 
                 track, lat, lon, vertical_rate, squawk, alert, emergency, spi, is_on_ground)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            message_data = []
            for msg in messages:
                message_data.append((
                    msg.get('icao24'),
                    msg.get('message_type'),
                    msg.get('timestamp'),
                    msg.get('callsign'),
                    msg.get('altitude'),
                    msg.get('ground_speed'),
                    msg.get('track'),
                    msg.get('lat'),
                    msg.get('lon'),
                    msg.get('vertical_rate'),
                    msg.get('squawk'),
                    msg.get('alert'),
                    msg.get('emergency'),
                    msg.get('spi'),
                    msg.get('is_on_ground')
                ))
            
            cursor.executemany(message_sql, message_data)
            inserted = cursor.rowcount
            
            # Insert position data
            self._insert_positions(cursor, messages)
            
            conn.commit()
            logger.debug(f"Inserted {inserted} messages into database")
            
        except MySQLError as e:
            conn.rollback()
            logger.error(f"Batch insert failed: {e}")
            raise
    
    return inserted
    
    def _upsert_aircraft(self, cursor, messages: List[Dict[str, Any]]):
        """Update or insert aircraft information"""
        aircraft_sql = """
            INSERT INTO aircraft (icao24, callsign, first_seen, last_seen)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                callsign = COALESCE(VALUES(callsign), callsign),
                last_seen = VALUES(last_seen)
        """
        
        aircraft_data = []
        seen_icao = set()
        
        for msg in messages:
            icao = msg.get('icao24')
            if icao and icao not in seen_icao:
                seen_icao.add(icao)
                aircraft_data.append((
                    icao,
                    msg.get('callsign'),
                    msg.get('timestamp'),
                    msg.get('timestamp')
                ))
        
        if aircraft_data:
            cursor.executemany(aircraft_sql, aircraft_data)
    
    def _insert_positions(self, cursor, messages: List[Dict[str, Any]]):
        """Insert position data for messages with location"""
        position_sql = """
            INSERT INTO positions (icao24, timestamp, lat, lon, altitude, ground_speed, track, vertical_rate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        position_data = []
        for msg in messages:
            if msg.get('lat') is not None and msg.get('lon') is not None:
                position_data.append((
                    msg.get('icao24'),
                    msg.get('timestamp'),
                    msg.get('lat'),
                    msg.get('lon'),
                    msg.get('altitude'),
                    msg.get('ground_speed'),
                    msg.get('track'),
                    msg.get('vertical_rate')
                ))
        
        if position_data:
            cursor.executemany(position_sql, position_data)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        stats = {}
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                # Total aircraft
                cursor.execute("SELECT COUNT(*) as count FROM aircraft")
                stats['total_aircraft'] = cursor.fetchone()['count']
                
                # Total messages
                cursor.execute("SELECT COUNT(*) as count FROM messages")
                stats['total_messages'] = cursor.fetchone()['count']
                
                # Total positions
                cursor.execute("SELECT COUNT(*) as count FROM positions")
                stats['total_positions'] = cursor.fetchone()['count']
                
                # Recent activity (last hour)
                cursor.execute("""
                    SELECT COUNT(*) as count FROM messages 
                    WHERE timestamp > DATE_SUB(NOW(), INTERVAL 1 HOUR)
                """)
                stats['messages_last_hour'] = cursor.fetchone()['count']
                
        except MySQLError as e:
            logger.error(f"Failed to get stats: {e}")
        
        return stats
    
    def health_check(self) -> bool:
        """Check database health"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return result[0] == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
            