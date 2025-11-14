-- ADS-B Data Ingestion Service Database Schema
-- MySQL 8.4 Compatible

-- Create database
CREATE DATABASE IF NOT EXISTS adsb
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE adsb;

-- Aircraft master table
CREATE TABLE IF NOT EXISTS aircraft (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    icao24 VARCHAR(6) NOT NULL UNIQUE,
    callsign VARCHAR(8) NULL,
    first_seen DATETIME NOT NULL,
    last_seen DATETIME NOT NULL,
    INDEX idx_icao24 (icao24),
    INDEX idx_last_seen (last_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Messages table (all message types)
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    icao24 VARCHAR(6) NOT NULL,
    message_type VARCHAR(10) NOT NULL,
    timestamp DATETIME NOT NULL,
    callsign VARCHAR(8) NULL,
    altitude INT NULL COMMENT 'Altitude in feet',
    ground_speed DECIMAL(8,2) NULL COMMENT 'Ground speed in knots',
    track DECIMAL(5,2) NULL COMMENT 'Track/heading in degrees',
    lat DECIMAL(10,6) NULL COMMENT 'Latitude',
    lon DECIMAL(11,6) NULL COMMENT 'Longitude',
    vertical_rate INT NULL COMMENT 'Vertical rate in feet/minute',
    squawk VARCHAR(4) NULL,
    alert BOOLEAN NULL,
    emergency BOOLEAN NULL,
    spi BOOLEAN NULL,
    is_on_ground BOOLEAN NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_icao24_timestamp (icao24, timestamp),
    INDEX idx_timestamp (timestamp),
    INDEX idx_message_type (message_type),
    FOREIGN KEY (icao24) REFERENCES aircraft(icao24) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Positions table (optimized for spatial queries)
CREATE TABLE IF NOT EXISTS positions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    icao24 VARCHAR(6) NOT NULL,
    timestamp DATETIME NOT NULL,
    lat DECIMAL(10,6) NOT NULL,
    lon DECIMAL(11,6) NOT NULL,
    altitude INT NULL,
    ground_speed DECIMAL(8,2) NULL,
    track DECIMAL(5,2) NULL,
    vertical_rate INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_icao24_timestamp (icao24, timestamp),
    INDEX idx_timestamp (timestamp),
    INDEX idx_location (lat, lon),
    FOREIGN KEY (icao24) REFERENCES aircraft(icao24) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Create a spatial index for geographic queries (requires POINT type)
-- ALTER TABLE positions ADD COLUMN location POINT NULL;
-- CREATE SPATIAL INDEX idx_spatial_location ON positions(location);

-- Partitioning for messages table (by month) - Optional for large datasets
-- This helps with performance and data management
-- Note: Uncomment and adjust based on your data retention needs

-- ALTER TABLE messages
-- PARTITION BY RANGE (TO_DAYS(timestamp)) (
--     PARTITION p_2024_01 VALUES LESS THAN (TO_DAYS('2024-02-01')),
--     PARTITION p_2024_02 VALUES LESS THAN (TO_DAYS('2024-03-01')),
--     PARTITION p_future VALUES LESS THAN MAXVALUE
-- );

-- Create a view for latest aircraft positions
CREATE OR REPLACE VIEW latest_positions AS
SELECT 
    a.icao24,
    a.callsign,
    p.timestamp,
    p.lat,
    p.lon,
    p.altitude,
    p.ground_speed,
    p.track
FROM aircraft a
INNER JOIN (
    SELECT icao24, MAX(timestamp) as max_timestamp
    FROM positions
    GROUP BY icao24
) latest ON a.icao24 = latest.icao24
INNER JOIN positions p ON p.icao24 = latest.icao24 
    AND p.timestamp = latest.max_timestamp;

-- Statistics view
CREATE OR REPLACE VIEW statistics AS
SELECT
    (SELECT COUNT(*) FROM aircraft) as total_aircraft,
    (SELECT COUNT(*) FROM messages) as total_messages,
    (SELECT COUNT(*) FROM positions) as total_positions,
    (SELECT COUNT(*) FROM aircraft WHERE last_seen > DATE_SUB(NOW(), INTERVAL 1 HOUR)) as active_last_hour,
    (SELECT COUNT(*) FROM messages WHERE timestamp > DATE_SUB(NOW(), INTERVAL 1 HOUR)) as messages_last_hour;

-- Create service user with appropriate permissions
-- Run these commands separately as root/admin user:

-- CREATE USER IF NOT EXISTS 'adsb_user'@'localhost' IDENTIFIED BY 'change_this_password';
-- GRANT SELECT, INSERT, UPDATE ON adsb.* TO 'adsb_user'@'localhost';
-- FLUSH PRIVILEGES;

-- For remote access:
-- CREATE USER IF NOT EXISTS 'adsb_user'@'%' IDENTIFIED BY 'change_this_password';
-- GRANT SELECT, INSERT, UPDATE ON adsb.* TO 'adsb_user'@'%';
-- FLUSH PRIVILEGES;