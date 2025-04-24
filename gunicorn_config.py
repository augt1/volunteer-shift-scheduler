import multiprocessing

# Gunicorn configuration file
bind = "unix:/run/gunicorn.sock"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 2
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
worker_connections = 1000

# Logging
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"

# SSL (if terminating SSL at Gunicorn)
# keyfile = "/etc/letsencrypt/live/your-domain.com/privkey.pem"
# certfile = "/etc/letsencrypt/live/your-domain.com/fullchain.pem"
