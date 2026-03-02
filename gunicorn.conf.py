"""
Gunicorn Production Configuration
===================================
Tuned for production deployment behind Nginx.
"""

import multiprocessing
import os

# ---- Server Socket ----
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = 2048

# ---- Worker Processes ----
# Formula: (2 * CPU cores) + 1
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"  # Use "gevent" for async if needed
worker_connections = 1000
timeout = 30
keepalive = 5
max_requests = 1000          # Restart workers after N requests (prevents memory leaks)
max_requests_jitter = 50     # Add randomness to prevent all workers restarting at once

# ---- Security ----
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# ---- Logging ----
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ---- Process Naming ----
proc_name = "expense-tracker-api"

# ---- Server Hooks ----
def on_starting(server):
    """Called just before the server starts."""
    pass

def post_fork(server, worker):
    """Called after a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_exec(server):
    """Called before a new process is forked."""
    server.log.info("Forked child, re-executing.")

def when_ready(server):
    """Called after server is ready to handle requests."""
    server.log.info("Server is ready. Spawning workers.")
