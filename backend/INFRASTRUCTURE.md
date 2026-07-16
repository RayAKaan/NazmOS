# NazmOS Infrastructure Guide

Production-ready infrastructure setup for NazmOS.

## Quick Start

### Prerequisites

- Docker 24.0+
- Docker Compose 2.20+
- Git
- Domain name configured with DNS A/AAAA records

### Initial Setup

1. Clone the repository:
```bash
git clone https://github.com/nazmos/backend.git
cd backend
```

2. Copy environment variables:
```bash
cp .env.production .env
# Edit .env with your production values
```

3. Generate secrets:
```bash
# Generate SECRET_KEY
openssl rand -base64 32

# Generate database password
openssl rand -hex 16
```

4. Create SSL certificates (Let's Encrypt):
```bash
# Using certbot
certbot certonly --nginx -d api.nazmos.in -d app.nazmos.in

# Copy certificates to nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/chain.pem nginx/ssl/
```

5. Initialize the database:
```bash
docker-compose -f docker-compose.prod.yml up -d postgres
# Wait for postgres to be healthy
docker-compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

6. Start all services:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI application |
| Nginx | 80, 443 | Reverse proxy, SSL termination |
| PostgreSQL | 5432 | Primary database |
| Redis | 6379 | Cache, Celery broker |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Dashboards |

## Monitoring

### Prometheus Metrics

Access metrics at: `http://localhost:9090`

Key metrics to monitor:
- `nazmos_http_requests_total` - Total HTTP requests
- `nazmos_http_request_duration_seconds` - Request latency
- `nazmos_database_connections_active` - DB connection pool
- `nazmos_cache_hits_total` - Cache hit rate

### Grafana Dashboards

Access at: `http://localhost:3000` (admin/admin)

Pre-configured dashboards:
- **API Performance** - Request latency, throughput
- **Database Performance** - Query times, connection pool
- **Cache Performance** - Hit rate, memory usage
- **Business Metrics** - Revenue, orders, inventory

## Maintenance

### Database Backups

```bash
# Manual backup
docker-compose -f docker-compose.prod.yml exec postgres pg_dump -U nazmos nazmos > backup_$(date +%Y%m%d).sql

# Automated backups (configured in crontab)
0 2 * * * docker exec nazmos-postgres pg_dump -U nazmos nazmos | gzip > /backups/db_$(date +\%Y\%m\%d).sql.gz
```

### Log Rotation

Logs are automatically rotated by Docker's logging driver. Configure in `docker-compose.prod.yml`:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "5"
```

### Security Updates

```bash
# Update base images
docker-compose -f docker-compose.prod.yml pull

# Rebuild application
docker-compose -f docker-compose.prod.yml build --no-cache api

# Restart services
docker-compose -f docker-compose.prod.yml up -d
```

## Troubleshooting

### Check service health
```bash
docker-compose -f docker-compose.prod.yml ps
```

### View logs
```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f api
```

### Restart services
```bash
docker-compose -f docker-compose.prod.yml restart api
```

### Database migrations
```bash
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head
```

## SSL Certificate Renewal

Let's Encrypt certificates auto-renew every 90 days. To manually renew:

```bash
certbot renew
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

## Disaster Recovery

### Full System Recovery

1. Restore database:
```bash
gunzip < backup_20240101.sql.gz | docker-compose -f docker-compose.prod.yml exec -T postgres psql -U nazmos nazmos
```

2. Restart services:
```bash
docker-compose -f docker-compose.prod.yml restart
```

### Point-in-Time Recovery

PostgreSQL WAL archiving enables point-in-time recovery. Configure in `docker-compose.prod.yml` and use `pg_restore` with appropriate recovery target.

## Scaling

### Horizontal Scaling (API)

```yaml
# Add more API instances
api:
  # ... existing config ...
  deploy:
    replicas: 3
```

### Vertical Scaling

Adjust resource limits in `docker-compose.prod.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 4G
```

## Security Checklist

- [ ] Change all default passwords
- [ ] Enable MFA for all admin accounts
- [ ] Configure firewall rules
- [ ] Enable audit logging
- [ ] Configure backup schedule
- [ ] Test disaster recovery
- [ ] Review SSL/TLS configuration
- [ ] Update security headers
- [ ] Configure intrusion detection
- [ ] Review access controls
