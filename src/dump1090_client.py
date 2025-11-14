"""
Dump1090 Client
Handles TCP connection to Dump1090 and reads BaseStation format data
"""

import socket
import logging
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class Dump1090Client:
    """Client for connecting to Dump1090 BaseStation output"""
    
    def __init__(self, host: str, port: int, reconnect_interval: int = 5, 
                 max_reconnect_interval: int = 60):
        """
        Initialize Dump1090 client
        
        Args:
            host: Dump1090 host address
            port: Dump1090 port (typically 30003 for BaseStation format)
            reconnect_interval: Initial reconnection interval in seconds
            max_reconnect_interval: Maximum reconnection interval
        """
        self.host = host
        self.port = port
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_interval = max_reconnect_interval
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.buffer = ""
        
    def connect(self) -> bool:
        """
        Establish connection to Dump1090
        
        Returns:
            True if connected successfully
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))
            self.connected = True
            logger.info(f"Connected to Dump1090 at {self.host}:{self.port}")
            return True
        except socket.error as e:
            logger.error(f"Failed to connect to Dump1090: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close connection to Dump1090"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.connected = False
        logger.info("Disconnected from Dump1090")
    
    def read_messages(self, callback: Callable[[str], None], running_flag: Callable[[], bool]):
        """
        Read messages from Dump1090 and call callback for each line
        
        Args:
            callback: Function to call with each complete message line
            running_flag: Function that returns True while service should run
        """
        current_reconnect_interval = self.reconnect_interval
        
        while running_flag():
            if not self.connected:
                if self.connect():
                    current_reconnect_interval = self.reconnect_interval
                else:
                    logger.warning(f"Reconnecting in {current_reconnect_interval} seconds...")
                    time.sleep(current_reconnect_interval)
                    current_reconnect_interval = min(
                        current_reconnect_interval * 2, 
                        self.max_reconnect_interval
                    )
                    continue
            
            try:
                # Read data from socket
                data = self.socket.recv(4096)
                if not data:
                    logger.warning("Connection closed by Dump1090")
                    self.disconnect()
                    continue
                
                # Decode and add to buffer
                self.buffer += data.decode('utf-8', errors='ignore')
                
                # Process complete lines
                while '\n' in self.buffer:
                    line, self.buffer = self.buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        try:
                            callback(line)
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                
            except socket.timeout:
                # Timeout is normal, continue
                continue
            except socket.error as e:
                logger.error(f"Socket error: {e}")
                self.disconnect()
            except Exception as e:
                logger.error(f"Unexpected error reading messages: {e}")
                self.disconnect()
        
        self.disconnect()
        