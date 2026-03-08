import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  stages: [
    { duration: "10s", target: 10 },  // ramp to 10 VUs
    { duration: "30s", target: 10 },  // hold
    { duration: "10s", target: 30 },  // ramp to 30 VUs
    { duration: "30s", target: 30 },  // hold
    { duration: "10s", target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<1000"],  // p95 < 1s
    http_req_failed: ["rate<0.95"],     // Most will fail (invalid signature) — that's expected
  },
};

// Simulates concurrent webhook delivery with invalid signatures.
// We're testing throughput, not business logic — expect 400s.
const payload = JSON.stringify({
  id: "evt_test_load",
  type: "checkout.session.completed",
  data: {
    object: {
      id: "cs_test_load",
      metadata: { user_id: "load-test", credit_amount: "20", pack_id: "top_up_20" },
    },
  },
});

export default function () {
  const res = http.post(`${BASE_URL}/api/billing/webhook`, payload, {
    headers: {
      "Content-Type": "application/json",
      "stripe-signature": "t=0,v1=invalid_signature_for_load_test",
    },
  });

  check(res, {
    "webhook responded (any status)": (r) => r.status > 0,
    "webhook < 500ms": (r) => r.timings.duration < 500,
    "not 500 error": (r) => r.status < 500,
  });

  sleep(0.3);
}
