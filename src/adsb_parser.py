"""
ADS-B Parser
Parses BaseStation (SBS-1) format ADS-B messages
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ADSBParser:
    """Parser for BaseStation format ADS-B messages"""
    
    # Message type mappings
    MESSAGE_TYPES = {
        'SEL': 'Selection Change',
        'ID': 'New ID',
        'AIR': 'New Aircraft',
        'STA': 'Status Change',
        'CLK': 'Click',
        'MSG': 'Transmission Message'
    }
    
    # Transmission type descriptions
    TRANSMISSION_TYPES = {
        1: 'ES_IDENT_AND_CATEGORY',
        2: 'ES_SURFACE_POS',
        3: 'ES_AIRBORNE_POS',
        4: 'ES_AIRBORNE_VEL',
        5: 'SURVEILLANCE_ALT',
        6: 'SURVEILLANCE_ID',
        7: 'AIR_TO_AIR',
        8: 'ALL_CALL_REPLY'
    }
    
    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parse a BaseStation format message
        
        Format: MSG,transmission_type,session_id,aircraft_id,icao24,flight_id,
                date_generated,time_generated,date_logged,time_logged,
                callsign,altitude,ground_speed,track,lat,lon,vertical_rate,
                squawk,alert,emergency,spi,is_on_ground
        
        Args:
            line: Raw message line
            
        Returns:
            Dictionary with parsed fields or None if parsing fails
        """
        try:
            fields = line.split(',')
            
            if len(fields) < 10:
                logger.debug(f"Message too short: {len(fields)} fields")
                return None
            
            message_type = fields[0]
            
            if message_type not in self.MESSAGE_TYPES:
                logger.debug(f"Unknown message type: {message_type}")
                return None
            
            # Parse common fields
            parsed = {
                'message_type': message_type,
                'transmission_type': self._parse_int(fields[1]) if len(fields) > 1 else None,
                'session_id': self._parse_int(fields[2]) if len(fields) > 2 else None,
                'aircraft_id': self._parse_int(fields[3]) if len(fields) > 3 else None,
                'icao24': fields[4].strip() if len(fields) > 4 else None,
                'flight_id': self._parse_int(fields[5]) if len(fields) > 5 else None,
            }
            
            # Parse timestamp
            if len(fields) > 8:
                parsed['timestamp'] = self._parse_timestamp(
                    fields[6], fields[7]  # date_generated, time_generated
                )
            
            # Parse message-specific fields (MSG type)
            if message_type == 'MSG' and len(fields) >= 22:
                parsed.update({
                    'callsign': fields[10].strip() if fields[10] else None,
                    'altitude': self._parse_int(fields[11]),
                    'ground_speed': self._parse_float(fields[12]),
                    'track': self._parse_float(fields[13]),
                    'lat': self._parse_float(fields[14]),
                    'lon': self._parse_float(fields[15]),
                    'vertical_rate': self._parse_int(fields[16]),
                    'squawk': fields[17].strip() if fields[17] else None,
                    'alert': self._parse_bool(fields[18]),
                    'emergency': self._parse_bool(fields[19]),
                    'spi': self._parse_bool(fields[20]),
                    'is_on_ground': self._parse_bool(fields[21])
                })
            
            # Validate required fields
            if not parsed.get('icao24') or not parsed.get('timestamp'):
                return None
            
            return parsed
            
        except Exception as e:
            logger.debug(f"Failed to parse message: {e} - Line: {line[:100]}")
            return None
    
    def _parse_int(self, value: str) -> Optional[int]:
        """Safely parse integer"""
        try:
            return int(value) if value and value.strip() else None
        except ValueError:
            return None
    
    def _parse_float(self, value: str) -> Optional[float]:
        """Safely parse float"""
        try:
            return float(value) if value and value.strip() else None
        except ValueError:
            return None
    
    def _parse_bool(self, value: str) -> Optional[bool]:
        """Safely parse boolean"""
        if not value or not value.strip():
            return None
        value = value.strip()
        if value == '0' or value.lower() == 'false':
            return False
        if value == '1' or value.lower() == 'true':
            return True
        if value == '-1':
            return True
        return None
    
    def _parse_timestamp(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse date and time strings into datetime object"""
        try:
            if not date_str or not time_str:
                return datetime.utcnow()
            
            # Format: YYYY/MM/DD and HH:MM:SS.mmm
            datetime_str = f"{date_str} {time_str}"
            return datetime.strptime(datetime_str, "%Y/%m/%d %H:%M:%S.%f")
        except ValueError:
            try:
                # Try without milliseconds
                datetime_str = f"{date_str} {time_str}"
                return datetime.strptime(datetime_str, "%Y/%m/%d %H:%M:%S")
            except ValueError:
                return datetime.utcnow()
                