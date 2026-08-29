import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  discardResponseBodies: true,
  scenarios: {
    downloads: {
      executor: "per-vu-iterations",
      vus: 30,
      iterations: 1,
      maxDuration: "10m",
    },
  },
  thresholds: {
    checks: ["rate>0.99"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  const clientId = `k6-${__VU}-${__ITER}-${Date.now()}`;
  const joinResponse = http.post(
    `${baseUrl}/queue/join`,
    JSON.stringify({ client_id: clientId }),
    { headers: { "Content-Type": "application/json" } }
  );

  if (!check(joinResponse, { "joined download queue": (r) => r.status === 200 })) return;

  let queueState = joinResponse.json();
  const ticket = queueState.ticket;
  while (!queueState.ready) {
    sleep(3);
    const statusResponse = http.get(`${baseUrl}/queue/status?ticket=${encodeURIComponent(ticket)}`);
    if (!check(statusResponse, { "queue status available": (r) => r.status === 200 })) return;
    queueState = statusResponse.json();
    if (queueState.expired) return;
  }

  const response = http.get(`${baseUrl}/download/model2?ticket=${encodeURIComponent(ticket)}`, {
    headers: { Range: "bytes=0-1048575" },
  });

  check(response, {
    "server supports queued partial download": (r) => r.status === 206,
  });

  // Bai test chi tai 1 MiB, nen chu dong tra slot thay vi cho resume timeout.
  http.post(`${baseUrl}/queue/leave?ticket=${encodeURIComponent(ticket)}`);
}
