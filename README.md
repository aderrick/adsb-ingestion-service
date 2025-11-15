# ADS-B Data Ingestion Service

Service for ingesting ADS-B (Automatic Dependent Surveillance-Broadcast) data from Dump1090 and storing it in MySQL.

## Features

- Connects to Dump1090 BaseStation format output (TCP port 30003)
- Automatic reconnection and retry logic
- Batch processing with configurable size and timeout
- Connection pooling for database writes
- Optional message deduplication
- Systemd service integration
- Configuration via YAML with environment variable overrides

## Architecture

```
┌─────────────┐         ┌──────────────────────┐         ┌──────────┐
│  Dump1090   │────────>│  Ingestion Service   │────────>│  MySQL   │
│  (TCP:30003)│         │                      │         │ Database │
└─────────────┘         └──────────────────────┘         └──────────┘
                                  │
                                  ├─ Data Parser (BaseStation format)
                                  ├─ Batch Processor (100 msgs/1sec)
                                  ├─ Deduplicator
                                  └─ Connection Manager
```

### Components

1. Config Manager: Loads configuration from YAML with environment variable overrides
2. Dump1090 Client: TCP client with automatic reconnection
3. ADS-B Parser: Parses BaseStation (SBS-1) format messages
4. Data Processor: Batches messages for efficient database insertion
5. Database Manager: MySQL connection pooling and query execution

## Installation

### Prerequisites

- Linux (Debian/Ubuntu recommended)
- Python 3.8 or higher
- MySQL 8.4 or compatible version
- Dump1090 or similar ADS-B receiver

### Quick Start

1. Clone repository to /opt/adsb-ingestion-service

2. Run installation script:

```bash
sudo chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

3. Setup MySQL database:

```bash
mysql -u root -p < database/schema.sql
```

Or manually create user and database:

```sql
CREATE USER 'adsb_user'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT SELECT, INSERT, UPDATE ON adsb.* TO 'adsb_user'@'localhost';
FLUSH PRIVILEGES;
```

4. Configure service:

```bash
sudo nano /etc/adsb-ingestion/config.yaml
```

Update database credentials and Dump1090 connection details.

5. Start service:

```bash
sudo chmod +x scripts/setup_service.sh
sudo ./scripts/setup_service.sh
sudo systemctl start adsb-ingestion
```

6. Verify operation:

```bash
sudo systemctl status adsb-ingestion
sudo journalctl -u adsb-ingestion -f
```

## Configuration

### Configuration File

Located at `/etc/adsb-ingestion/config.yaml`:

```yaml
dump1090:
  host: localhost
  port: 30003
  
database:
  host: localhost
  port: 3306
  database: adsb
  user: adsb_user
  password: your_password
  
processing:
  batch_size: 100
  batch_timeout: 1.0
  enable_deduplication: true
```

### Environment Variables

Configuration can be overridden with environment variables:

- `DUMP1090_HOST`: Dump1090 server hostname
- `DUMP1090_PORT`: Dump1090 port number
- `DB_HOST`: MySQL hostname
- `DB_PORT`: MySQL port
- `DB_NAME`: Database name
- `DB_USER`: Database user
- `DB_PASSWORD`: Database password
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

## Database Schema

### Tables

- aircraft: Master aircraft registry (icao24, callsign, first_seen, last_seen)
- messages: All ADS-B messages with position, velocity, altitude data
- positions: Time-series position data optimized for spatial queries

### Views

- latest_positions: Current position of all aircraft
- statistics: Service statistics and metrics

## Usage

### Starting/Stopping Service

```bash
# Start
sudo systemctl start adsb-ingestion

# Stop
sudo systemctl stop adsb-ingestion

# Restart
sudo systemctl restart adsb-ingestion

# Enable auto-start on boot
sudo systemctl enable adsb-ingestion
```

### Viewing Logs

```bash
# Real-time logs
sudo journalctl -u adsb-ingestion -f

# Recent logs
sudo tail -f /var/log/adsb-ingestion/service.log

# All logs
sudo journalctl -u adsb-ingestion
```

### Querying Data

```sql
-- Current aircraft positions
SELECT * FROM latest_positions;

-- Aircraft seen in last hour
SELECT * FROM aircraft 
WHERE last_seen > DATE_SUB(NOW(), INTERVAL 1 HOUR);

-- Message statistics
SELECT * FROM statistics;

-- Recent positions for specific aircraft
SELECT * FROM positions 
WHERE icao24 = 'ABC123' 
ORDER BY timestamp DESC 
LIMIT 100;
```

## Performance Tuning

### Database

- Adjust `batch_size` for write performance (default: 100)
- Consider table partitioning for large datasets
- Add spatial indexes for geographic queries
- Regular OPTIMIZE TABLE maintenance

### Application

- Increase `pool_size` for high message rates
- Adjust `batch_timeout` for latency vs throughput
- Disable deduplication if not needed
- Monitor queue size in statistics

### System

- Increase file descriptor limits in systemd service
- Use SSD storage for database
- Monitor memory usage
- Consider MySQL tuning parameters

## Troubleshooting

### Service won't start

```bash
# Check status
sudo systemctl status adsb-ingestion

# Check logs
sudo journalctl -u adsb-ingestion -n 50

# Verify configuration
sudo python3 /opt/adsb-ingestion/main.py /etc/adsb-ingestion/config.yaml
```

### Cannot connect to Dump1090

- Verify Dump1090 is running: `netstat -tlnp | grep 30003`
- Check firewall rules
- Test connection: `telnet localhost 30003`
- Verify host/port in configuration

### Database connection errors

- Verify MySQL is running: `sudo systemctl status mysql`
- Test credentials: `mysql -u adsb_user -p -h localhost adsb`
- Check MySQL user permissions
- Verify connection pool settings

### High memory usage

- Reduce `batch_size` and `pool_size`
- Check for slow database queries
- Monitor message rate
- Consider rate limiting

## Maintenance

### Log Rotation

Logs are automatically rotated based on configuration. Manual rotation:

```bash
sudo logrotate -f /etc/logrotate.d/adsb-ingestion
```

### Database Maintenance

```sql
-- Optimize tables
OPTIMIZE TABLE messages;
OPTIMIZE TABLE positions;

-- Archive old data
DELETE FROM messages WHERE timestamp < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

### Backup

```bash
# Backup database
mysqldump -u root -p adsb > adsb_backup_$(date +%Y%m%d).sql

# Backup configuration
sudo cp -r /etc/adsb-ingestion /backup/
```

## Development

### Running manually

```bash
cd /opt/adsb-ingestion
source venv/bin/activate
python3 main.py /etc/adsb-ingestion/config.yaml
```

### Testing

```bash
# Test database connection
python3 -c "from database_manager import DatabaseManager; from config_manager import ConfigManager; cfg = ConfigManager(); db = DatabaseManager(cfg.get_database_config()); print(db.health_check())"

# Test Dump1090 connection
nc localhost 30003
```

## Security Considerations

- Change default database password
- Use firewall rules to restrict database access
- Run service as non-root user (adsb)
- Regular security updates
- Monitor logs for suspicious activity
- Use SSL for remote database connections

## License

This software is provided as-is for ADS-B data collection purposes.

## Support

For issues and questions:
- Check logs: `/var/log/adsb-ingestion/service.log`
- Review configuration
- Verify network connectivity
- Check system resources

## Version History

- 1.0.0 (2024): Initial release
  - BaseStation format support
  - MySQL 8.4 compatibility
  - Systemd integration
  - Batch processing
  - Automatic reconnection