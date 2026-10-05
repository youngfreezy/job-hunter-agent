#!/usr/bin/env node
// Stop only processes recorded by this checkout, never all Node/Python servers.
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { setTimeout: delay } = require("node:timers/promises");

function parsePid(value) {
  return /^[1-9]\d*$/.test(value.trim()) && Number.isSafeInteger(Number(value))
    && Number(value) > 1 ? Number(value) : null;
}

function ownsProcess(root, kind, info) {
  if (!info) return false;
  const expected = kind === "frontend" ? path.join(root, "frontend") : root;
  if (info.cwd !== expected) return false;
  if (kind === "launcher") return /(?:^|\s)(?:\S*\/)?scripts\/start\.js(?:\s|$)/.test(info.command);
  if (kind === "backend") return /\buvicorn\s+backend\.gateway\.main:app(?:\s|$)/.test(info.command);
  return kind === "frontend" && /(?:npm run dev|next(?:-server| dev))/.test(info.command);
}

function inspectProcess(pid) {
  try {
    const command = execFileSync("ps", ["-p", String(pid), "-o", "command="], { encoding: "utf8" }).trim();
    const started = execFileSync("ps", ["-p", String(pid), "-o", "lstart="], { encoding: "utf8" }).trim();
    const cwdLine = execFileSync("lsof", ["-a", "-p", String(pid), "-d", "cwd", "-Fn"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] })
      .split("\n").find(line => line.startsWith("n"));
    return cwdLine ? { pid, command, started, cwd: fs.realpathSync(cwdLine.slice(1)) } : null;
  } catch { return null; }
}

function isRunning(pid) {
  try { process.kill(pid, 0); return true; }
  catch (error) { return error.code !== "ESRCH"; }
}

function descendants(pid) {
  try {
    return execFileSync("pgrep", ["-P", String(pid)], { encoding: "utf8" })
      .trim().split("\n").map(parsePid).filter(Boolean);
  } catch { return []; }
}

async function stopTree(info, root) {
  for (const child of descendants(info.pid)) {
    const current = inspectProcess(child);
    if (current && (current.cwd === root || current.cwd.startsWith(root + path.sep))) await stopTree(current, root);
  }
  // A stale/reused PID is insufficient: recheck identity before each signal.
  const sameProcess = () => {
    const current = inspectProcess(info.pid);
    return current?.started === info.started && current.command === info.command && current.cwd === info.cwd;
  };
  if (!sameProcess()) return;
  try { process.kill(info.pid, "SIGTERM"); } catch { return; }
  await delay(500);
  if (sameProcess()) {
    try { process.kill(info.pid, "SIGKILL"); } catch { /* Already stopped. */ }
  }
}

async function main() {
  const root = fs.realpathSync(path.join(__dirname, ".."));
  let refused = false;
  for (const kind of ["backend", "frontend", "launcher"]) {
    const file = path.join(root, ".runtime", `${kind}.pid`);
    if (!fs.existsSync(file)) continue;
    const value = fs.readFileSync(file, "utf8");
    const pid = parsePid(value);
    const info = pid ? inspectProcess(pid) : null;
    if (!pid || (isRunning(pid) && !ownsProcess(root, kind, info))) {
      console.error(`Refusing to stop unverified ${kind} process; check ${file}.`);
      refused = true;
      continue;
    }
    if (info) await stopTree(info, root);
    if (fs.existsSync(file) && fs.readFileSync(file, "utf8") === value) fs.unlinkSync(file);
  }
  if (refused) process.exitCode = 1;
  else console.log("JobHunter Agent stopped");
}

module.exports = { parsePid, ownsProcess };
if (require.main === module) main().catch(() => { console.error("Unable to safely stop JobHunter Agent."); process.exitCode = 1; });
