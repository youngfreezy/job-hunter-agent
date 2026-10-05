const assert = require("node:assert/strict");
const { test } = require("node:test");
const { parsePid, ownsProcess } = require("./stop-app");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const { once } = require("node:events");

test("process identifiers cannot address process groups or the init process", () => {
  for (const input of ["-1", "0", "1", "12foo", "--help", "1.5", "999999999999999999"]) assert.equal(parsePid(input), null);
  assert.equal(parsePid("123\n"), 123);
});

test("only a recorded service running in this exact checkout is owned", () => {
  const root = "/work/job-hunter";
  assert(ownsProcess(root, "backend", { cwd: root, command: "python -m uvicorn backend.gateway.main:app --port 8000" }));
  assert(ownsProcess(root, "launcher", { cwd: root, command: "node scripts/start.js" }));
  assert(ownsProcess(root, "frontend", { cwd: root + "/frontend", command: "npm run dev" }));
  assert(!ownsProcess(root, "backend", { cwd: "/work/other", command: "python -m uvicorn backend.gateway.main:app" }));
  assert(!ownsProcess(root, "backend", { cwd: root, command: "python -m uvicorn other:app" }));
  assert(!ownsProcess(root, "frontend", { cwd: "/work/other/frontend", command: "next dev" }));
  assert(!ownsProcess(root, "launcher", null));
});

test("stop script terminates its own fixture but refuses an unrelated live PID", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "jobhunter-stop-test-"));
  fs.mkdirSync(path.join(root, "scripts"));
  fs.mkdirSync(path.join(root, ".runtime"));
  fs.copyFileSync(path.join(__dirname, "stop-app.js"), path.join(root, "scripts/stop-app.js"));
  fs.writeFileSync(path.join(root, "scripts/start.js"), "process.send('ready'); setTimeout(() => {}, 30000);");
  const child = spawn(process.execPath, ["scripts/start.js"], { cwd: root, stdio: ["ignore", "ignore", "ignore", "ipc"] });
  try {
    await once(child, "message");
    const exited = once(child, "exit");
    fs.writeFileSync(path.join(root, ".runtime/launcher.pid"), String(child.pid));
    // The test runner is outside the fixture checkout and must remain alive.
    fs.writeFileSync(path.join(root, ".runtime/backend.pid"), String(process.pid));
    const stopped = spawnSync(process.execPath, ["scripts/stop-app.js"], { cwd: root, encoding: "utf8", timeout: 10000 });
    assert.equal(stopped.status, 1);
    assert.match(stopped.stderr, /Refusing to stop unverified backend/);
    await exited;
    assert(!fs.existsSync(path.join(root, ".runtime/launcher.pid")));
    assert(fs.existsSync(path.join(root, ".runtime/backend.pid")));
  } finally {
    if (child.exitCode === null && child.signalCode === null) child.kill();
    fs.rmSync(root, { recursive: true, force: true });
  }
});
