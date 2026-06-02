/**
 * Python runtime resolution and venv setup.
 *
 * This module is host-agnostic. It encapsulates:
 *   - Where the plugin-local venv lives
 *   - How to bootstrap a Python interpreter on a fresh checkout
 *   - How to detect whether the venv is ready (runtime-ready.json marker)
 *
 * It is used by every adapter (OpenClaw plugin, MCP server, standalone CLI)
 * so the rules about "do not use system Python" stay in one place.
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RUNTIME_MARKER_SCHEMA = "kbprep.plugin_venv.v2";
const PYTHON_WORKER_DEPENDENCY_SPEC = "mineru[all]==3.2.1;PyMuPDF==1.27.2.3";

export interface RuntimeConfig {
  device_override?: "auto" | "cuda" | "cpu";
  max_cpu_threads?: number;
  min_free_memory_gb?: number;
  mineru_timeout_seconds?: number;
  python_path?: string;
}

function pluginRootDir(): string {
  const moduleDir = dirname(fileURLToPath(import.meta.url));
  // The compiled `dist/` folder is one level below the package root.
  if (basename(moduleDir) === "dist" || basename(moduleDir) === "src" || basename(moduleDir) === "adapters") {
    return resolve(moduleDir, "..", "..", "..");
  }
  return moduleDir;
}

function pluginPythonProjectDir(): string {
  return join(pluginRootDir(), "python");
}

function pluginVenvDir(): string {
  return join(pluginRootDir(), ".kbprep", "venv");
}

function pluginVenvPythonPath(): string {
  return process.platform === "win32"
    ? join(pluginVenvDir(), "Scripts", "python.exe")
    : join(pluginVenvDir(), "bin", "python");
}

function pluginVenvReadyMarker(): string {
  return join(pluginRootDir(), ".kbprep", "runtime-ready.json");
}

function shouldSkipAutoSetupForTests(): boolean {
  return process.env.KBPREP_SKIP_AUTO_SETUP === "1" || !!process.env.VITEST;
}

function isPluginVenvReady(config?: RuntimeConfig): boolean {
  if (!existsSync(pluginVenvPythonPath()) || !existsSync(pluginVenvReadyMarker())) {
    return false;
  }
  try {
    const marker = JSON.parse(readFileSync(pluginVenvReadyMarker(), "utf-8")) as Record<string, unknown>;
    if (marker.schema !== RUNTIME_MARKER_SCHEMA) return false;
    if (marker.plugin_version !== pluginPackageVersion()) return false;
    if (marker.python_executable !== pluginVenvPythonPath()) return false;
    const expected = config?.device_override && config.device_override !== "auto"
      ? config.device_override
      : "auto";
    if (marker.device_override !== expected) return false;
    const spec = (marker.python_project as Record<string, unknown> | undefined)?.dependency_spec;
    if (spec !== PYTHON_WORKER_DEPENDENCY_SPEC) return false;
    if (marker.setup_env && (marker.setup_env as Record<string, unknown>).cuda_setup_failure) {
      // Re-attempt only if user explicitly changed device_override.
      if (expected === "auto" || expected === "cuda") return false;
    }
    return true;
  } catch {
    return false;
  }
}

function pluginPackageVersion(): string {
  try {
    const pkg = JSON.parse(readFileSync(join(pluginRootDir(), "package.json"), "utf-8")) as Record<string, unknown>;
    return String(pkg.version ?? "0.0.0");
  } catch {
    return "0.0.0";
  }
}

export function resolvePythonPath(startPath: string, config?: RuntimeConfig): string {
  const pluginPython = pluginVenvPythonPath();
  if (isPluginVenvReady(config)) return pluginPython;
  if (shouldSkipAutoSetupForTests()) {
    if (config?.python_path?.trim()) return config.python_path.trim();
    return process.env.KBPREP_PYTHON ?? process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
  }
  return pluginPython;
}

export async function ensurePythonRuntime(config?: RuntimeConfig): Promise<string> {
  const pythonPath = pluginVenvPythonPath();
  if (isPluginVenvReady(config)) return pythonPath;
  if (shouldSkipAutoSetupForTests()) return resolvePythonPath(pluginRootDir(), config);

  const venvDir = pluginVenvDir();
  cleanupStalePluginRuntime(config);
  mkdirSync(dirname(venvDir), { recursive: true });
  const bootstrap = bootstrapPythonCommand(config);
  await runSetupCommand(bootstrap.command, [...bootstrap.args, "-m", "venv", venvDir], "create plugin-local Python venv", 5 * 60_000);
  await runSetupCommand(pythonPath, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], "upgrade pip", 10 * 60_000);
  await runSetupCommand(pythonPath, ["-m", "pip", "install", "-e", pluginPythonProjectDir()], "install kbprep worker", 60 * 60_000);
  const setupResult = await runSetupCommand(
    pythonPath,
    ["-m", "kbprep_worker.cli", "setup-env", "--json-stdin"],
    "detect hardware and tune deps",
    30 * 60_000,
    JSON.stringify({ device_override: config?.device_override ?? "auto" }),
  );
  writeFileSync(pluginVenvReadyMarker(), JSON.stringify({
    schema: RUNTIME_MARKER_SCHEMA,
    created_at: new Date().toISOString(),
    plugin_version: pluginPackageVersion(),
    python_executable: pythonPath,
    device_override: config?.device_override && config.device_override !== "auto" ? config.device_override : "auto",
    python_project: {
      path: pluginPythonProjectDir(),
      dependency_spec: PYTHON_WORKER_DEPENDENCY_SPEC,
    },
    setup_env: parseSetupEnvelope(setupResult.stdout),
  }, null, 2), "utf-8");
  return pythonPath;
}

function cleanupStalePluginRuntime(_config?: RuntimeConfig): void {
  // If the marker says cuda_setup_failure and user wants cuda, wipe so we retry.
  try {
    const markerPath = pluginVenvReadyMarker();
    if (!existsSync(markerPath)) return;
    const marker = JSON.parse(readFileSync(markerPath, "utf-8")) as Record<string, unknown>;
    const setupEnv = marker.setup_env as Record<string, unknown> | undefined;
    if (setupEnv?.cuda_setup_failure) {
      const venvDir = pluginVenvDir();
      if (existsSync(venvDir)) {
        spawn(process.platform === "win32" ? "rmdir" : "rm", [process.platform === "win32" ? "/S" : "-rf", venvDir], { stdio: "ignore" });
      }
      spawn(process.platform === "win32" ? "del" : "rm", [markerPath], { stdio: "ignore" });
    }
  } catch {
    /* ignore */
  }
}

function bootstrapPythonCommand(config?: RuntimeConfig): { command: string; args: string[] } {
  if (config?.python_path?.trim()) {
    return { command: config.python_path.trim(), args: [] };
  }
  if (process.env.KBPREP_PYTHON) return { command: process.env.KBPREP_PYTHON, args: [] };
  if (process.platform === "win32") return { command: "py", args: ["-3"] };
  return { command: "python3", args: [] };
}

async function runSetupCommand(
  command: string,
  args: string[],
  purpose: string,
  timeoutMs: number,
  stdinJson?: string,
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`Setup step '${purpose}' timed out after ${timeoutMs}ms`));
    }, timeoutMs);
    child.stdout.on("data", (c: Buffer) => (stdout += c.toString("utf-8")));
    child.stderr.on("data", (c: Buffer) => (stderr += c.toString("utf-8")));
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(`Setup step '${purpose}' exited ${code}: ${stderr.trim().slice(0, 500)}`));
    });
    if (stdinJson !== undefined) {
      child.stdin.write(stdinJson);
      child.stdin.end();
    }
  });
}

function parseSetupEnvelope(stdout: string): Record<string, unknown> {
  try {
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch {
    return { raw_stdout: stdout.slice(0, 1024) };
  }
}
