#!/usr/bin/env node
/**
 * JobHunter Agent — full-stack startup script
 *
 * Usage:  npm start              (from project root)
 *         npm run start:no-docker (skip Docker — uses cloud services)
 *         node scripts/start.js
 *
 * What it does:
 *   1. Opens Docker Desktop if the daemon isn't running, waits up to 2 min
 *   2. Starts Postgres + Redis containers (docker compose up -d)
 *   3. Waits for Postgres and Redis to accept connections
 *   4. Starts FastAPI backend   → http://localhost:8000
 *   5. Starts Next.js frontend  → http://localhost:3000
 *   6. Ctrl-C shuts all children down cleanly
 */

const { execSync, spawn } = require("child_process");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");
const SKIP_DOCKER = process.argv.includes("--no-docker");

// ── colour helpers ────────────────────────────────────────────────────────────
const c = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  blue: "\x1b[34m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  red: "\x1b[31m",
  cyan: "\x1b[36m",
  magenta: "\x1b[35m",
};
const tag = (label, color) => `${color}${c.bold}[${label}]${c.reset}`;
const DB_TAG = tag("db", c.blue);
const REDIS_TAG = tag("redis", c.magenta);
const API_TAG = tag("backend", c.green);
const UI_TAG = tag("frontend", c.cyan);
const SYS_TAG = tag("startup", c.yellow);

const log = (prefix, line) => console.log(`${prefix} ${line}`);

// ── helpers ───────────────────────────────────────────────────────────────────
function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: "pipe", ...opts }).toString().trim();
}

function isDockerRunning() {
  try {
    run("docker info");
    return true;
  } catch {
    return false;
  }
}

async function waitFor(label, fn, intervalMs = 2000, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

// ── tracked child processes ───────────────────────────────────────────────────
const children = [];

function spawnChild(label, prefix, cmd, args, opts = {}) {
  const child = spawn(cmd, args, {
    cwd: opts.cwd,
    env: { ...process.env, ...(opts.env || {}) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  children.push(child);

  child.stdout.on("data", (d) => {
    d.toString()
      .split("\n")
      .filter(Boolean)
      .forEach((line) => log(prefix, line));
  });
  child.stderr.on("data", (d) => {
    d.toString()
      .split("\n")
      .filter(Boolean)
      .forEach((line) => log(prefix, line));
  });

  child.on("exit", (code) => {
    if (code !== 0 && code !== null) {
      log(prefix, `${c.red}exited with code ${code}${c.reset}`);
    }
  });

  return child;
}

// ── graceful shutdown ─────────────────────────────────────────────────────────
function shutdown() {
  log(SYS_TAG, "Shutting down…");
  children.forEach((ch) => {
    try {
      ch.kill("SIGTERM");
    } catch {}
  });
  setTimeout(() => process.exit(0), 1500);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

// ── find python venv ──────────────────────────────────────────────────────────
function findPython() {
  const venvPython = path.join(BACKEND, "venv", "bin", "python");
  try {
    run(`${venvPython} --version`);
    return venvPython;
  } catch {}

  // Fallback: try homebrew python3.11
  try {
    const brew = "/opt/homebrew/opt/python@3.11/bin/python3.11";
    run(`${brew} --version`);
    return brew;
  } catch {}

  return "python3";
}

// ── main ──────────────────────────────────────────────────────────────────────
(async () => {
  console.log(
    `\n${c.bold}${c.cyan}  ╔═══════════════════════════════════════╗${c.reset}`
  );
  console.log(
    `${c.bold}${c.cyan}  ║       JobHunter Agent — Startup       ║${c.reset}`
  );
  console.log(
    `${c.bold}${c.cyan}  ╚═══════════════════════════════════════╝${c.reset}\n`
  );

  // 1. Docker
  if (!SKIP_DOCKER) {
    if (!isDockerRunning()) {
      log(SYS_TAG, "Docker daemon not running — opening Docker Desktop…");
      try {
        run("open -a Docker");
      } catch {}
      await waitFor(
        "Docker daemon",
        async () => isDockerRunning(),
        5000,
        120_000
      );
      await new Promise((r) => setTimeout(r, 3000));
    }
    log(SYS_TAG, `Docker is running ${c.green}✓${c.reset}`);

    // 2. Start Postgres + Redis containers
    log(DB_TAG, "Starting Postgres + Redis containers…");
    try {
      run("docker compose up -d", { cwd: ROOT });
    } catch (e) {
      log(DB_TAG, `docker compose: ${e.message.split("\n")[0]}`);
    }

    // 3. Wait for Postgres
    log(DB_TAG, "Waiting for Postgres to be ready…");
    await waitFor(
      "Postgres",
      async () => {
        try {
          run(
            "docker exec jobhunter_db pg_isready -U jobhunter -d jobhunter"
          );
          return true;
        } catch {
          return false;
        }
      },
      2000,
      60_000
    );
    log(DB_TAG, `Postgres ready ${c.green}✓${c.reset}`);

    // 4. Wait for Redis
    log(REDIS_TAG, "Waiting for Redis to be ready…");
    await waitFor(
      "Redis",
      async () => {
        try {
          run("docker exec jobhunter_redis redis-cli ping");
          return true;
        } catch {
          return false;
        }
      },
      2000,
      30_000
    );
    log(REDIS_TAG, `Redis ready ${c.green}✓${c.reset}`);
  } else {
    log(
      SYS_TAG,
      `Skipping Docker ${c.yellow}(using cloud services)${c.reset}`
    );
  }

  // 5. FastAPI backend
  log(API_TAG, "Starting FastAPI backend on :8000…");
  const python = findPython();
  spawnChild(
    "backend",
    API_TAG,
    python,
    [
      "-m",
      "uvicorn",
      "backend.gateway.main:app",
      "--host",
      "0.0.0.0",
      "--port",
      "8000",
      "--reload",
      "--reload-exclude",
      "backend/venv/*",
      "--reload-exclude",
      "*/venv/*",
      "--reload-exclude",
      "frontend/*",
      "--reload-exclude",
      "node_modules/*",
      "--reload-exclude",
      "test_*",
      "--reload-exclude",
      "*.log",
    ],
    { cwd: ROOT }
  );

  // Wait briefly for backend to bind
  await new Promise((r) => setTimeout(r, 3000));

  // 6. Next.js frontend
  log(UI_TAG, "Starting Next.js frontend on :3000…");
  const nodeBin = "/opt/homebrew/opt/node@20/bin";
  const npmBin = path.join(nodeBin, "npm");
  spawnChild("frontend", UI_TAG, npmBin, ["run", "dev"], {
    cwd: FRONTEND,
    env: { PATH: `${nodeBin}:${process.env.PATH}` },
  });

  log(SYS_TAG, `\n  ${c.bold}All services started.${c.reset}`);
  log(SYS_TAG, `  Backend  → http://localhost:8000/api/health`);
  log(SYS_TAG, `  Frontend → http://localhost:3000`);
  log(SYS_TAG, `  Press Ctrl-C to stop everything.\n`);
})();
