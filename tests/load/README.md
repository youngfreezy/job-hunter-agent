# Load Tests

k6 scripts for stress testing the JobHunter Agent backend.

## Install k6

```bash
brew install k6
```

## Run Tests

### Health endpoint baseline
```bash
k6 run tests/load/k6-health.js
```

### Against Railway (production)
```bash
k6 run -e BASE_URL=https://api.jobhunteragent.com tests/load/k6-health.js
```

### Session creation (requires auth token)
```bash
k6 run -e BASE_URL=https://api.jobhunteragent.com -e AUTH_TOKEN=<jwt> tests/load/k6-session-create.js
```

### Webhook throughput
```bash
k6 run -e BASE_URL=https://api.jobhunteragent.com tests/load/k6-webhook.js
```

## Interpreting Results

| Metric | Target |
|--------|--------|
| Health p95 | < 500ms |
| Session create p95 | < 2s |
| Webhook p95 | < 1s |
| Error rate (health) | < 1% |

## Notes

- Session create test uses `materials_only` mode and `max_jobs: 5` to minimize backend load
- Webhook test sends invalid signatures intentionally — we're measuring throughput, not business logic
- SSE connections timeout after 5s by design — we only test the connection handshake
