import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";

export const options = {
  stages: [
    { duration: "10s", target: 5 },   // ramp to 5 VUs
    { duration: "30s", target: 5 },   // hold
    { duration: "10s", target: 10 },  // ramp to 10 VUs
    { duration: "30s", target: 10 },  // hold
    { duration: "10s", target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // p95 < 2s for session create
    http_req_failed: ["rate<0.05"],     // <5% errors (rate limits expected)
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${AUTH_TOKEN}`,
};

const payload = JSON.stringify({
  keywords: ["software engineer"],
  locations: ["Remote"],
  remote_only: true,
  search_radius: 100,
  country: "US",
  resume_text: "John Doe\njohn@example.com\n5 years software engineering experience.",
  preferences: {},
  config: {
    max_jobs: 5,
    tailoring_quality: "standard",
    application_mode: "materials_only",
    generate_cover_letters: false,
    job_boards: ["linkedin"],
  },
});

export default function () {
  // Session creation (returns immediately, pipeline runs in background)
  const res = http.post(`${BASE_URL}/api/sessions`, payload, { headers });

  check(res, {
    "session created 200/201": (r) => r.status === 200 || r.status === 201,
    "session has id": (r) => {
      try {
        return JSON.parse(r.body).session_id !== undefined;
      } catch {
        return false;
      }
    },
    "create < 2s": (r) => r.timings.duration < 2000,
  });

  // If session created, try opening SSE stream briefly
  if (res.status === 200 || res.status === 201) {
    try {
      const sessionId = JSON.parse(res.body).session_id;
      const sse = http.get(`${BASE_URL}/api/sessions/${sessionId}/stream`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
        timeout: "5s",
      });
      check(sse, {
        "SSE connection opened": (r) => r.status === 200,
      });
    } catch {
      // SSE timeout is expected — we only hold for 5s
    }
  }

  sleep(2);
}
