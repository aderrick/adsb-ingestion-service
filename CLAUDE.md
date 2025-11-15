# CLAUDE.md - ADS-B Ingestion Service

This document provides comprehensive guidance for AI assistants working with the ADS-B Data Ingestion Service codebase.

## Project Overview

**Purpose**: Production-ready headless service for ingesting ADS-B (Automatic Dependent Surveillance-Broadcast) aircraft data from Dump1090 devices and storing it in MySQL.

**Technology Stack**:
- Python 3.8+
- MySQL 8.0+ (schema compatible with MySQL 8.4)
- TCP sockets for Dump1090 communication
- Systemd for service management

**Key Features**:
- Continuous real-time data ingestion from Dump1090 BaseStation format (port 30003)
- Batch processing for high-performance database writes
- Automatic reconnection with exponential backoff
- Message deduplication
- Connection pooling
- Comprehensive logging and statistics

## Project Structure

```
adsb-ingestion-service/
├── src/                          # Source code
│   ├── main.py                   # Main entry point and service orchestration
│   ├── config_manager.py         # Configuration loading (YAML + env vars)
│   ├── dump1090_client.py        # TCP client for Dump1090 connection
│   ├── adsb_parser.py            # BaseStation format message parser
│   ├── data_processor.py         # Batching and deduplication logic
│   ├── database_manager.py       # MySQL connection pool and operations
│   └── __init__.py
├── database/
│   └── schema.sql                # Complete database schema with views
├── config/
│   └── config.yaml.example       # Example configuration file
├── scripts/
│   ├── install.sh                # System installation script
│   └── setup_service.sh          # Systemd service setup
├── systemd/
│   └── adsb-ingestion.service    # Systemd service definition
├── .env.example                  # Environment variables template
├── requirements.txt              # Python dependencies
└── README.md                     # User documentation

Deployment Locations:
- Application: /opt/adsb-ingestion/
- Configuration: /etc/adsb-ingestion/config.yaml
- Logs: /var/log/adsb-ingestion/service.log
- Service: /etc/systemd/system/adsb-ingestion.service
```

## Architecture & Data Flow

```
┌─────────────┐         ┌──────────────────────┐         ┌──────────┐
│  Dump1090   │────────>│  Ingestion Service   │────────>│  MySQL   │
│  (TCP:30003)│         │                      │         │ Database │
└─────────────┘         └──────────────────────┘         └──────────┘
                                  │
                                  ├─ Dump1090Client (TCP connection)
                                  ├─ ADSBParser (BaseStation format)
                                  ├─ DataProcessor (batching/dedup)
                                  └─ DatabaseManager (connection pool)
```

**Data Flow**:
1. `Dump1090Client` establishes TCP connection to Dump1090 on port 30003
2. Raw BaseStation format messages arrive line-by-line
3. `ADSBParser` parses each line into structured dictionary
4. `DataProcessor` batches messages and applies deduplication
5. `DatabaseManager` performs batch inserts using connection pool
6. Data written to three tables: `aircraft`, `messages`, `positions`

## Core Components

### 1. main.py (src/main.py)
**Purpose**: Service orchestration and lifecycle management

**Key Classes**:
- `ADSBIngestionService`: Main service class that coordinates all components

**Important Functions**:
- `setup_logging(log_config)`: Configures rotating file and console logging
- `signal_handler(signum, frame)`: Handles SIGINT/SIGTERM for graceful shutdown
- `is_running()`: Global flag function for thread coordination
- `message_callback(line)`: Callback for processing incoming messages
- `print_stats()`: Periodic statistics logging (runs every 60 seconds)

**Threading Model**:
- Main thread: Message reading loop
- Background thread 1: Periodic batch flushing (checks every 100ms)
- Background thread 2: Statistics printing (every 60s)

**Lifecycle**:
1. Load configuration
2. Initialize all components
3. Start background threads
4. Read messages in main loop
5. On shutdown: flush pending data, disconnect, log final stats

### 2. config_manager.py (src/config_manager.py)
**Purpose**: Hierarchical configuration management

**Configuration Precedence** (highest to lowest):
1. Environment variables
2. YAML configuration file
3. Default values in `DEFAULT_CONFIG`

**Key Methods**:
- `_load_config(config_path)`: Loads YAML file
- `_deep_merge(base, override)`: Recursively merges configurations
- `_apply_env_overrides()`: Applies environment variable overrides
- `_validate_config()`: Validates required fields

**Environment Variables**:
```
DUMP1090_HOST, DUMP1090_PORT
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
LOG_LEVEL, LOG_FILE
```

**Configuration Sections**:
- `dump1090`: Connection settings and reconnection parameters
- `database`: MySQL connection and pool settings
- `processing`: Batch size, timeout, deduplication settings
- `logging`: Log level, file location, rotation settings

### 3. dump1090_client.py (src/dump1090_client.py)
**Purpose**: TCP client with automatic reconnection

**Key Features**:
- Exponential backoff reconnection (5s → 60s max)
- Socket timeout handling (10s)
- Line-buffered message reading
- Graceful connection management

**Key Methods**:
- `connect()`: Establishes TCP connection
- `disconnect()`: Closes connection safely
- `read_messages(callback, running_flag)`: Main read loop with reconnection logic

**Error Handling**:
- Socket errors trigger disconnect and reconnection
- Empty data (connection closed) triggers reconnection
- Callback exceptions are logged but don't break the connection

**Important**: Uses `running_flag()` callable to check if service should continue

### 4. adsb_parser.py (src/adsb_parser.py)
**Purpose**: Parse BaseStation (SBS-1) format ADS-B messages

**BaseStation Format**:
```
MSG,transmission_type,session_id,aircraft_id,icao24,flight_id,
date_generated,time_generated,date_logged,time_logged,
callsign,altitude,ground_speed,track,lat,lon,vertical_rate,
squawk,alert,emergency,spi,is_on_ground
```

**Message Types**:
- `MSG`: Transmission Message (primary type used)
- `SEL`, `ID`, `AIR`, `STA`, `CLK`: Other types (logged but not processed)

**Transmission Types** (field 2 for MSG):
1. ES_IDENT_AND_CATEGORY
2. ES_SURFACE_POS
3. ES_AIRBORNE_POS
4. ES_AIRBORNE_VEL
5. SURVEILLANCE_ALT
6. SURVEILLANCE_ID
7. AIR_TO_AIR
8. ALL_CALL_REPLY

**Key Methods**:
- `parse(line)`: Main parsing function, returns dict or None
- `_parse_int/float/bool()`: Safe type conversion with None fallback
- `_parse_timestamp()`: Converts date/time strings to datetime object

**Validation**:
- Requires minimum fields (icao24, timestamp)
- Gracefully handles malformed data
- Returns None for unparseable messages

### 5. data_processor.py (src/data_processor.py)
**Purpose**: Message batching, deduplication, and flow control

**Batching Logic**:
- Flushes when batch reaches `batch_size` (default: 100)
- Flushes when `batch_timeout` seconds elapsed (default: 1.0s)
- Periodic flush thread checks every 100ms

**Deduplication**:
- Message key: `{icao24}:{timestamp}:{transmission_type}`
- Maintains rolling cache of 1000 recent message keys
- Time-based deduplication window (configurable)

**Key Methods**:
- `add_message(message)`: Queue message with dedup check
- `_flush_batch()`: Write batch to database
- `force_flush()`: Immediate flush (used on shutdown)
- `periodic_flush(running_flag)`: Background thread for timeout-based flushing
- `get_stats()`: Return statistics dictionary

**Thread Safety**:
- Uses `threading.Lock()` for queue access
- All public methods are thread-safe

**Statistics Tracked**:
- `messages_received`: Total messages received
- `messages_processed`: Successfully written to DB
- `messages_discarded`: Filtered as duplicates
- `batches_written`: Number of batch operations
- `errors`: Database write failures
- `queue_size`: Current queue length

### 6. database_manager.py (src/database_manager.py)
**Purpose**: MySQL connection pooling and batch operations

**Connection Pool**:
- Uses `mysql.connector.pooling.MySQLConnectionPool`
- Default pool size: 5 connections
- Autocommit disabled (explicit transaction control)
- UTF-8mb4 character set

**Key Methods**:
- `get_connection()`: Context manager for connections (auto-commit/rollback)
- `batch_insert_messages(messages)`: Atomic batch insert
- `_upsert_aircraft(cursor, messages)`: Update aircraft table
- `_insert_positions(cursor, messages)`: Insert position data
- `get_stats()`: Query database statistics
- `health_check()`: Simple connectivity test

**Transaction Flow** (batch_insert_messages):
1. **FIRST**: Upsert aircraft (satisfies foreign key constraints)
2. **SECOND**: Insert into messages table
3. **THIRD**: Insert into positions (only for messages with lat/lon)
4. Commit transaction (or rollback on error)

**Important**: Foreign key constraints require aircraft to exist before messages can be inserted. Order matters!

## Database Schema

### Tables

**aircraft** (Master aircraft registry):
```sql
- id: BIGINT (primary key)
- icao24: VARCHAR(6) UNIQUE (aircraft identifier)
- callsign: VARCHAR(8) NULL
- first_seen: DATETIME
- last_seen: DATETIME
Indexes: icao24, last_seen
```

**messages** (All ADS-B messages):
```sql
- id: BIGINT (primary key)
- icao24: VARCHAR(6) (foreign key → aircraft.icao24)
- message_type: VARCHAR(10)
- timestamp: DATETIME
- callsign, altitude, ground_speed, track
- lat, lon, vertical_rate
- squawk, alert, emergency, spi, is_on_ground
- created_at: TIMESTAMP
Indexes: (icao24, timestamp), timestamp, message_type
```

**positions** (Time-series position data):
```sql
- id: BIGINT (primary key)
- icao24: VARCHAR(6) (foreign key → aircraft.icao24)
- timestamp: DATETIME
- lat, lon (DECIMAL)
- altitude, ground_speed, track, vertical_rate
- created_at: TIMESTAMP
Indexes: (icao24, timestamp), timestamp, (lat, lon)
```

### Views

**latest_positions**: Current position of each aircraft
```sql
SELECT a.icao24, a.callsign, p.timestamp, p.lat, p.lon,
       p.altitude, p.ground_speed, p.track
FROM aircraft a
JOIN (latest timestamp per icao24) latest
JOIN positions p
```

**statistics**: Service metrics
```sql
SELECT total_aircraft, total_messages, total_positions,
       active_last_hour, messages_last_hour
```

### Foreign Key Relationships

```
aircraft.icao24 ←── messages.icao24 (ON DELETE CASCADE)
aircraft.icao24 ←── positions.icao24 (ON DELETE CASCADE)
```

## Configuration Guide

### YAML Configuration
Location: `/etc/adsb-ingestion/config.yaml`

```yaml
dump1090:
  host: localhost           # Dump1090 hostname/IP
  port: 30003              # BaseStation format port
  reconnect_interval: 5    # Initial reconnect delay (seconds)
  max_reconnect_interval: 60  # Max reconnect delay

database:
  host: localhost
  port: 3306
  database: adsb
  user: adsb_user
  password: change_this_password
  pool_size: 5            # Connection pool size
  pool_name: adsb_pool

processing:
  batch_size: 100         # Messages per batch
  batch_timeout: 1.0      # Max seconds before flush
  enable_deduplication: true
  dedup_window: 2         # Dedup window (seconds)

logging:
  level: INFO             # DEBUG, INFO, WARNING, ERROR
  file: /var/log/adsb-ingestion/service.log
  max_bytes: 10485760     # 10MB
  backup_count: 5         # Keep 5 rotated logs
```

### Environment Variable Overrides

Environment variables take precedence over YAML:
```bash
DUMP1090_HOST=192.168.1.100
DUMP1090_PORT=30003
DB_HOST=localhost
DB_PORT=3306
DB_NAME=adsb
DB_USER=adsb_user
DB_PASSWORD=secure_password
LOG_LEVEL=DEBUG
LOG_FILE=/var/log/adsb-ingestion/service.log
```

## Development Workflow

### Setup Development Environment

```bash
# Clone repository
cd /opt
sudo mkdir adsb-ingestion-service
cd adsb-ingestion-service

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Run with custom config
python3 src/main.py config/config.yaml.example

# Run with environment variables
export DB_PASSWORD=mypassword
export LOG_LEVEL=DEBUG
python3 src/main.py
```

### Testing Components

```bash
# Test database connection
python3 -c "
from src.config_manager import ConfigManager
from src.database_manager import DatabaseManager
cfg = ConfigManager('config/config.yaml.example')
db = DatabaseManager(cfg.get_database_config())
print('Health check:', db.health_check())
"

# Test Dump1090 connection (manual)
nc localhost 30003  # Should show ADS-B messages

# Test parser
python3 -c "
from src.adsb_parser import ADSBParser
parser = ADSBParser()
msg = 'MSG,3,1,1,ABC123,1,2024/01/01,12:00:00.000,2024/01/01,12:00:00.000,,10000,,,51.5,-0.1,,,0,0,0,0'
print(parser.parse(msg))
"
```

### Adding New Features

When modifying the codebase:

1. **Maintain Threading Model**: Be aware of thread-safe operations
2. **Preserve Data Flow**: Respect the pipeline: Client → Parser → Processor → Database
3. **Handle Errors Gracefully**: Never crash the main loop; log and continue
4. **Update Configuration**: Add new settings to ConfigManager.DEFAULT_CONFIG
5. **Update Schema**: Modify database/schema.sql for database changes
6. **Test Reconnection**: Ensure changes don't break auto-reconnection logic

## Code Conventions

### Python Style
- **Imports**: Standard library, third-party, local (separated by blank lines)
- **Docstrings**: All classes and public methods have docstrings
- **Type Hints**: Used in function signatures where beneficial
- **Naming**:
  - Classes: PascalCase
  - Functions/methods: snake_case
  - Constants: UPPER_SNAKE_CASE
  - Private methods: _leading_underscore

### Error Handling
- **Never crash the service**: Catch exceptions in loops and threads
- **Log errors with context**: Use `logger.error()` with `exc_info=True`
- **Graceful degradation**: Continue processing on non-fatal errors
- **Reconnection logic**: Auto-reconnect on connection failures

### Logging Practices
- **DEBUG**: Detailed message parsing, batch operations
- **INFO**: Connection status, statistics, lifecycle events
- **WARNING**: Recoverable issues (missing config, reconnection attempts)
- **ERROR**: Failed operations, exceptions

### Thread Safety
- All shared data structures must use locks
- Use context managers for lock acquisition
- Prefer `threading.Lock()` over lower-level primitives
- Check `running_flag()` in all loops for clean shutdown

## Common Development Tasks

### Adding a New Configuration Parameter

1. Add to `ConfigManager.DEFAULT_CONFIG` (src/config_manager.py)
2. Add environment variable override in `_apply_env_overrides()`
3. Update config/config.yaml.example
4. Update .env.example
5. Document in README.md

### Adding a New Database Field

1. Update database/schema.sql with ALTER TABLE or new CREATE TABLE
2. Modify `DatabaseManager.batch_insert_messages()` to include new field
3. Update parser if field comes from ADS-B messages
4. Test with fresh database: `mysql < database/schema.sql`

### Modifying Message Parsing

1. Edit `ADSBParser.parse()` method (src/adsb_parser.py)
2. Update returned dictionary with new fields
3. Ensure `None` handling for missing data
4. Update database schema if storing new fields
5. Test with real Dump1090 data

### Changing Batch Processing Logic

1. Modify `DataProcessor` class (src/data_processor.py)
2. Update `add_message()` or `_flush_batch()`
3. Consider thread safety implications
4. Test with high message rates
5. Monitor statistics to verify behavior

### Adding New Statistics

1. Add counter to `DataProcessor.stats` dictionary
2. Update `get_stats()` method
3. Add database query in `DatabaseManager.get_stats()` if needed
4. Update `main.py` print_stats() to display new metric
5. Consider adding to statistics view in schema.sql

## Deployment

### Installation Process

```bash
# 1. Run installation script
sudo chmod +x scripts/install.sh
sudo ./scripts/install.sh

# 2. Setup MySQL database
mysql -u root -p < database/schema.sql

# 3. Configure service
sudo nano /etc/adsb-ingestion/config.yaml
# Update database password and Dump1090 host

# 4. Install systemd service
sudo chmod +x scripts/setup_service.sh
sudo ./scripts/setup_service.sh

# 5. Start service
sudo systemctl start adsb-ingestion
sudo systemctl status adsb-ingestion
```

### Service Management

```bash
# Start/stop/restart
sudo systemctl start adsb-ingestion
sudo systemctl stop adsb-ingestion
sudo systemctl restart adsb-ingestion

# Enable/disable auto-start
sudo systemctl enable adsb-ingestion
sudo systemctl disable adsb-ingestion

# View logs
sudo journalctl -u adsb-ingestion -f         # Follow logs
sudo journalctl -u adsb-ingestion -n 100     # Last 100 lines
sudo tail -f /var/log/adsb-ingestion/service.log
```

### Files Installed

- Application: `/opt/adsb-ingestion/`
- Config: `/etc/adsb-ingestion/config.yaml`
- Logs: `/var/log/adsb-ingestion/service.log`
- Service: `/etc/systemd/system/adsb-ingestion.service`
- User: `adsb` (system user, no login)

## Troubleshooting

### Service Won't Start

**Check logs**:
```bash
sudo journalctl -u adsb-ingestion -n 50
sudo systemctl status adsb-ingestion
```

**Common causes**:
- Database connection failure → Check DB credentials
- Dump1090 not running → Verify `netstat -tlnp | grep 30003`
- Permission issues → Check `/var/log/adsb-ingestion` ownership
- Configuration errors → Validate YAML syntax

### Cannot Connect to Dump1090

**Verify Dump1090**:
```bash
netstat -tlnp | grep 30003
telnet localhost 30003
```

**Check configuration**:
- Correct host/port in config.yaml
- Firewall rules
- Dump1090 actually broadcasting BaseStation format

### Database Connection Errors

**Test connection**:
```bash
mysql -u adsb_user -p -h localhost adsb
```

**Common issues**:
- Wrong password in config.yaml
- User doesn't exist → Run schema.sql user creation
- MySQL not running → `sudo systemctl status mysql`
- Insufficient permissions → Check GRANT statements

### High Memory Usage

**Causes**:
- Large batch_size → Reduce to 50-100
- Large pool_size → Reduce to 3-5
- Message queue buildup → Check database write performance

**Monitor**:
```bash
# Check queue size in statistics
mysql -u adsb_user -p adsb -e "SELECT * FROM statistics;"

# Check Python memory
ps aux | grep main.py
```

### No Data in Database

**Check message flow**:
1. Service connected to Dump1090? → Check logs for "Connected to Dump1090"
2. Messages being parsed? → Set LOG_LEVEL=DEBUG, check logs
3. Messages being batched? → Check statistics in logs
4. Database writes succeeding? → Check for batch insert errors

**Verify**:
```bash
# Check service logs
sudo journalctl -u adsb-ingestion -f

# Check database
mysql -u adsb_user -p adsb -e "SELECT COUNT(*) FROM messages;"
mysql -u adsb_user -p adsb -e "SELECT * FROM statistics;"
```

## Performance Tuning

### High Message Rate (>1000 msg/sec)

**Increase batch size**:
```yaml
processing:
  batch_size: 500
  batch_timeout: 0.5
```

**Increase connection pool**:
```yaml
database:
  pool_size: 10
```

**MySQL tuning** (/etc/mysql/mysql.conf.d/mysqld.cnf):
```ini
[mysqld]
innodb_buffer_pool_size = 2G
innodb_log_file_size = 512M
innodb_flush_log_at_trx_commit = 2
```

### Low Latency Requirements

**Reduce batch timeout**:
```yaml
processing:
  batch_size: 50
  batch_timeout: 0.5
```

**Disable deduplication** (if acceptable):
```yaml
processing:
  enable_deduplication: false
```

### Database Maintenance

```sql
-- Optimize tables periodically
OPTIMIZE TABLE messages;
OPTIMIZE TABLE positions;

-- Archive old data
DELETE FROM messages WHERE timestamp < DATE_SUB(NOW(), INTERVAL 30 DAY);
DELETE FROM positions WHERE timestamp < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- Check table sizes
SELECT
    table_name,
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
FROM information_schema.TABLES
WHERE table_schema = 'adsb';
```

## Security Considerations

### Production Checklist

- [ ] Change default database password
- [ ] Use strong password (min 16 chars, mixed case, numbers, symbols)
- [ ] Restrict database access to localhost if possible
- [ ] Enable MySQL SSL for remote connections
- [ ] Use firewall rules (ufw/iptables) to restrict database port
- [ ] Run service as non-root user (adsb)
- [ ] Set proper file permissions (644 for config, 755 for directories)
- [ ] Regular security updates: `sudo apt-get update && sudo apt-get upgrade`
- [ ] Monitor logs for suspicious activity
- [ ] Rotate logs regularly
- [ ] Backup database regularly

### Systemd Security Features

The service file includes:
```
NoNewPrivileges=true      # Prevent privilege escalation
PrivateTmp=true           # Isolated /tmp
ProtectSystem=strict      # Read-only filesystem
ProtectHome=true          # No home directory access
ReadWritePaths=/var/log/adsb-ingestion  # Only log dir writable
```

## Git Development Workflow

### Current Branch
- Feature branch: `claude/claude-md-mhzvndlqev9n8q9o-01E9wYY3M1nCShybaG743J2a`
- Always commit and push to this branch

### Making Commits

```bash
# Check status
git status

# Stage files
git add <files>

# Commit with descriptive message
git commit -m "feat: Add new feature"
git commit -m "fix: Resolve bug in parser"
git commit -m "docs: Update CLAUDE.md"

# Push to remote (with retry on network errors)
git push -u origin claude/claude-md-mhzvndlqev9n8q9o-01E9wYY3M1nCShybaG743J2a
```

### Commit Message Conventions
- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Test additions/changes
- `chore:` Maintenance tasks

## Key File References

When referencing code locations, use this format: `file_path:line_number`

**Main entry point**: src/main.py:178 (main function)
**Service class**: src/main.py:82 (ADSBIngestionService)
**Message parsing**: src/adsb_parser.py:38 (parse method)
**Batch insertion**: src/database_manager.py:85 (batch_insert_messages)
**Configuration loading**: src/config_manager.py:48 (ConfigManager.__init__)
**TCP client**: src/dump1090_client.py:66 (read_messages)
**Data processing**: src/data_processor.py:48 (add_message)

## Important Notes for AI Assistants

1. **Preserve Service Reliability**: This is a production service. Never introduce changes that could cause crashes or data loss.

2. **Thread Safety First**: Multiple threads access shared state. Always use locks appropriately.

3. **Graceful Error Handling**: Errors should be logged but not crash the service. The main loop must never exit unexpectedly.

4. **Database Integrity**: Respect foreign key constraints. Aircraft must exist before messages can be inserted.

5. **Configuration Precedence**: Remember: ENV vars > YAML > Defaults

6. **Reconnection Logic**: Don't break the automatic reconnection. It's critical for production reliability.

7. **Performance Impact**: Consider message throughput (can be >1000/sec). Test performance implications of changes.

8. **Log Verbosity**: Keep INFO-level logs concise. Use DEBUG for detailed information.

9. **Backward Compatibility**: Database schema changes require migration strategy for existing deployments.

10. **Testing**: Always test with real Dump1090 data when possible. Synthetic data may not capture edge cases.

## Additional Resources

- **BaseStation Format**: SBS-1 protocol documentation (search "Mode-S Beast protocol")
- **ADS-B Overview**: FAA ADS-B documentation
- **Dump1090**: https://github.com/flightaware/dump1090
- **MySQL Connector/Python**: https://dev.mysql.com/doc/connector-python/en/

## Recent Changes

- **2025-11-15**: Refactored batch_insert_messages as class method (commit: d7c8462)
- **2025-11-15**: Updated install dependencies (commit: aab56d4)
- **2025-11-15**: Initial commit (commit: 3ba1884)

---

Last Updated: 2025-11-15
Version: 1.0.0
