import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  stages: [
    { duration: "10s", target: 20 },  // ramp to 20 VUs
    { duration: "30s", target: 20 },  // hold
    { duration: "10s", target: 50 },  // ramp to 50 VUs
    { duration: "30s", target: 50 },  // hold
    { duration: "10s", target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],   // p95 < 500ms
    http_req_failed: ["rate<0.01"],     // <1% errors
  },
};

export default function () {
  // Health check (DB + Redis connectivity)
  const ready = http.get(`${BASE_URL}/api/health/ready`);
  check(ready, {
    "health ready 200": (r) => r.status === 200,
    "health ready < 300ms": (r) => r.timings.duration < 300,
  });

  sleep(0.5);

  // Basic health (no dependency check)
  const health = http.get(`${BASE_URL}/api/health`);
  check(health, {
    "health 200": (r) => r.status === 200,
  });

  sleep(0.5);
}
