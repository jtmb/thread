# Thread — Deployment Guide

Thread runs anywhere: a $35 Raspberry Pi, an old laptop, a cloud VM, or any machine with Docker. Pick the option that fits your setup.

---

## Docker / Container

The easiest way to get Thread running. Single command, no Python setup, works on any architecture (amd64, arm64, armv7).

### Quick Start

```bash
# Clone and start
git clone https://github.com/jtmb/thread.git && cd thread
docker compose up -d

# Verify
curl http://localhost:5000/api/v1/health
```

### Build & Run Manually

```bash
# Build the image
docker build -t thread-server .

# Run with persistent data volume
docker run -d \
  --name thread-server \
  -p 5000:5000 \
  -v thread_data:/app/data \
  --restart unless-stopped \
  thread-server

# Check health
docker ps --filter name=thread-server
curl http://localhost:5000/api/v1/health
```

### Custom Configuration

Override any config via environment variables:

```bash
docker run -d \
  --name thread-server \
  -p 5000:5000 \
  -v thread_data:/app/data \
  -e THREAD_LOG_LEVEL=DEBUG \
  -e THREAD_POOL_SIZE=6 \
  -e THREAD_MAX_SEARCH_RESULTS=200 \
  thread-server
```

Or copy `.env.example` → `.env` and edit — Docker Compose picks it up automatically.

### Container Management

```bash
# View logs
docker logs -f thread-server

# Check resource usage
docker stats thread-server

# Restart after config change
docker compose restart

# Stop
docker compose down

# Stop and wipe data (fresh start)
docker compose down -v
```

### Data Persistence

The `thread_data` named volume stores the SQLite database and per-session git repos. It survives container rebuilds, image updates, and `docker compose down` (without `-v`).

```bash
# Backup the database
docker run --rm -v thread_data:/data alpine tar czf - -C /data . > thread-backup-$(date +%Y%m%d).tar.gz

# Restore
docker compose down
docker volume rm thread_thread_data
docker compose up -d  # Creates fresh volume
cat thread-backup-20260628.tar.gz | docker run --rm -i -v thread_data:/data alpine tar xzf - -C /data
```

### Multi-Architecture

The Dockerfile uses `python:3.12-slim` which is multi-arch. Builds and runs on:

| Platform | Example Hardware |
|----------|-----------------|
| `linux/amd64` | Workstation, cloud VM, Intel NUC |
| `linux/arm64` | Raspberry Pi 4/5, Apple Silicon, AWS Graviton |
| `linux/arm/v7` | Raspberry Pi 3B |

Build for a specific architecture:
```bash
docker build --platform linux/arm64 -t thread-server .
```

---

## Bare Metal (Raspberry Pi)

> Target: Raspberry Pi 3B (ARMv7, 1GB RAM) running Raspberry Pi OS Bookworm (64-bit).

### Quick Deploy

```bash
# From the repo root on your workstation, copy to Pi:
rsync -av --exclude '.git' --exclude '__pycache__' \
  thread_server/ deploy/ pi@<pi-ip>:~/thread-server/

# SSH to Pi and run setup:
ssh pi@<pi-ip>
cd ~/thread-server
chmod +x deploy/setup.sh
sudo THREAD_DIR=/home/pi/thread-server THREAD_PORT=5000 ./deploy/setup.sh
```

---

## Manual Setup

### 1. Directory Structure
```bash
mkdir -p ~/thread-server/data/git
mkdir -p ~/thread-server/logs
```

### 2. Python Virtual Environment
```bash
cd ~/thread-server
python3 -m venv venv
source venv/bin/activate
pip install -r thread_server/requirements.txt
```

### 3. Configuration
All config via environment variables (in systemd unit or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `THREAD_DB_PATH` | `data/thread.db` | SQLite database path |
| `THREAD_GIT_BASE` | `data/git/` | Per-session git repos |
| `THREAD_HOST` | `0.0.0.0` | Bind address |
| `THREAD_PORT` | `5000` | Listen port |
| `THREAD_POOL_SIZE` | `12` | Max DB connections (matches Waitress threads) |
| `THREAD_POOL_TIMEOUT` | `10` | Seconds to wait for a connection before 503 |
| `THREAD_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `THREAD_DEBUG` | `false` | Enable Flask debug mode (never in production) |
| `THREAD_MAX_SEARCH_RESULTS` | `100` | Hard cap on search results |
| `THREAD_CACHE_SIZE` | `512` | Session LRU cache entries |
| `THREAD_CACHE_TTL` | `30` | Session cache TTL (seconds) |
| `THREAD_SEARCH_CACHE_SIZE` | `128` | Search cache entries |
| `THREAD_SEARCH_CACHE_TTL` | `5` | Search cache TTL (seconds) |

### 4. systemd Service
```bash
sudo cp deploy/thread.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable thread
sudo systemctl start thread
```

### 5. Verify
```bash
curl http://localhost:5000/api/v1/health
# {"status":"ok","timestamp":"...","version":"0.1.0"}
```

---

## systemd Service Management

```bash
# Start / Stop / Restart
sudo systemctl start thread
sudo systemctl stop thread
sudo systemctl restart thread

# Status
sudo systemctl status thread

# View logs
sudo journalctl -u thread -f
sudo journalctl -u thread --since "10 minutes ago"

# Check memory
systemctl show thread | grep Memory
# MemoryCurrent=<bytes> — actual RSS
```

### Service File Reference
```
[Unit]
Description=Thread AI Context Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/thread-server
ExecStart=/home/pi/thread-server/venv/bin/python thread_server/server.py
Restart=always
RestartSec=5

# All config as environment variables
Environment=THREAD_HOST=0.0.0.0
Environment=THREAD_PORT=5000
Environment=THREAD_DB_PATH=/home/pi/thread-server/data/thread.db
Environment=THREAD_LOG_LEVEL=INFO
Environment=THREAD_DEBUG=false
Environment=THREAD_POOL_SIZE=12

# Memory limits
MemoryMax=800M
MemoryHigh=600M

# Logging to journald
StandardOutput=journal
StandardError=journal
SyslogIdentifier=thread-server

[Install]
WantedBy=multi-user.target
```

---

## Firewall

Thread serves on port 5000. For LAN access only:

```bash
# Allow from local network only
sudo ufw allow from 192.168.0.0/24 to any port 5000 proto tcp

# Or allow from everywhere (if using Tailscale/VPN)
sudo ufw allow 5000/tcp
```

---

## Monitoring

### Memory
```bash
# Check RSS
ps -o pid,rss,comm -p $(pgrep -f 'python.*server.py')

# systemd memory metrics
systemctl show thread -p MemoryCurrent -p MemoryPeak

# cgroup memory
systemd-cgtop
```

Expected: ~90-110MB at idle, ~160-195MB under load.

### Database
```bash
# DB size
ls -lh ~/thread-server/data/thread.db

# WAL file size (should stay small)
ls -lh ~/thread-server/data/thread.db-wal
```

### Health
```bash
# Basic health
curl http://localhost:5000/api/v1/health

# Detailed stats
curl http://localhost:5000/api/v1/stats | python -m json.tool
```

---

## Troubleshooting

### Service won't start
```bash
# Check for errors
sudo journalctl -u thread --no-pager -n 50

# Common causes:
# - Port already in use: sudo lsof -i :5000
# - Python venv not found: verify ExecStart path
# - Permission denied: check data/ directory ownership (should be pi:pi)
```

### High memory usage
```bash
# Check cache sizes (in stats endpoint)
curl http://localhost:5000/api/v1/stats | python -c "import sys,json; d=json.load(sys.stdin); print('Cache entries:', d['cache'])"

# Reduce cache sizes via env vars:
# THREAD_CACHE_SIZE=256 THREAD_SEARCH_CACHE_SIZE=64

# Check SQLite page cache impact:
# Reduce THREAD_POOL_SIZE to 6 (fewer connections = less memory)
```

### Slow queries
```bash
# Check WAL checkpoint
sqlite3 ~/thread-server/data/thread.db "PRAGMA wal_checkpoint(TRUNCATE);"

# Rebuild FTS5 index if corrupted
sqlite3 ~/thread-server/data/thread.db "INSERT INTO entries_fts(entries_fts) VALUES('rebuild');"

# Check index usage
sqlite3 ~/thread-server/data/thread.db "EXPLAIN QUERY PLAN SELECT * FROM entries WHERE session_id=1 ORDER BY created_at DESC;"
# Should show: USING COVERING INDEX idx_entries_session_created
```

### Git repos taking space
```bash
# Check per-session repo sizes
du -sh ~/thread-server/data/git/*/

# Clean up old sessions
rm -rf ~/thread-server/data/git/old-session-name/
```
