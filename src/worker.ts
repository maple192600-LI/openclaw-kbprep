/**
 * Python worker spawner for kbprep.
 * Uses child_process.spawn to call Python CLI.
 * No HTTP service, no daemon, no persistent worker.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, appendFile } from "node:fs/promises";
import { delimiter, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { makeError, type KBPrepError } from "./errors.js";

export interface WorkerResult<T = Record<string, unknown>> {
  ok: boolean;
  data?: T;
  metrics?: Record<string, unknown>;
  warnings?: string[];
  error?: KBPrepError;
}

export interface WorkerCallOptions {
  pythonPath: string;
  cwd?: string;
  timeoutMs: number;
  signal?: AbortSignal;
  logDir?: string;
  config?: WorkerConfig;
}

export interface WorkerConfig {
  device_override?: "auto" | "cuda" | "cpu";
  max_cpu_threads?: number;
  min_free_memory_gb?: number;
  mineru_timeout_seconds?: number;
}

/**
 * Call Python worker via CLI mode.
 * stdout: single JSON envelope
 * stderr: JSONL logs
 */
export async function callWorker<T = Record<string, unknown>>(
  command: string,
  input: Record<string, unknown>,
  options: WorkerCallOptions,
): Promise<WorkerResult<T>> {
  const { pythonPath, cwd, timeoutMs, signal, logDir } = options;
  const jobId = randomUUID().replace(/-/g, "").slice(0, 16);

  const args = ["-m", "kbprep_worker.cli", command, "--json-stdin"];

  const env = { ...process.env } as Record<string, string>;
  const pluginDir = dirname(fileURLToPath(import.meta.url));
  const bundledPythonDir = join(pluginDir, "..", "python");
  env.PYTHONPATH = bundledPythonDir;
  env.PYTHONNOUSERSITE = "1";
  if (/[\\/]Scripts[\\/]python\.exe$/i.test(pythonPath) || /[\\/]bin[\\/]python(?:\d+(?:\.\d+)?)?$/i.test(pythonPath)) {
    const venvDir = pythonPath.replace(/[\\/](Scripts[\\/]python\.exe|bin[\\/]python(?:\d+(?:\.\d+)?)?)$/i, "");
    const venvBin = process.platform === "win32"
      ? join(venvDir, "Scripts")
      : join(venvDir, "bin");
    env.PATH = `${venvBin}${delimiter}${env.PATH || ""}`;
  }
  env.PYTHONUTF8 = "1";
  env.PYTHONIOENCODING = "utf-8";

  // Pass plugin config as env vars
  if (options.config?.device_override && options.config.device_override !== "auto") {
    env.MINERU_DEVICE_MODE = options.config.device_override;
  }
  if (options.config?.max_cpu_threads) {
    env.TORCH_NUM_THREADS = String(options.config.max_cpu_threads);
    env.OMP_NUM_THREADS = String(options.config.max_cpu_threads);
  }
  if (options.config?.mineru_timeout_seconds) {
    env.KBPREP_MINERU_TIMEOUT_SECONDS = String(options.config.mineru_timeout_seconds);
  }

  const child: ChildProcess = spawn(pythonPath, args, {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
    signal,
    windowsHide: true,
    env,
  });

  let stdout = "";
  child.stdout!.on("data", (chunk: Buffer) => {
    stdout += chunk.toString("utf-8");
  });

  let stderr = "";
  const stderrLines: string[] = [];
  child.stderr!.on("data", (chunk: Buffer) => {
    const text = chunk.toString("utf-8");
    stderr += text;
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (trimmed) stderrLines.push(trimmed);
    }
  });

  // Write stderr JSONL to log file if logDir specified
  if (logDir) {
    await mkdir(logDir, { recursive: true });
    const logPath = join(logDir, `${jobId}.jsonl`);
    child.stderr!.on("data", async (chunk: Buffer) => {
      try {
        await appendFile(logPath, chunk);
      } catch {}
    });
  }

  const exitPromise = new Promise<{ code: number | null; sig: string | null }>((resolve, reject) => {
    const timer = setTimeout(() => {
      // Send SIGTERM first, wait 5s, then SIGKILL
      child.kill("SIGTERM");
      const killTimer = setTimeout(() => {
        child.kill("SIGKILL");
      }, 5000);
      child.on("close", () => {
        clearTimeout(killTimer);
      });
      reject(createTimeoutError(timeoutMs));
    }, timeoutMs);

    child.on("close", (code, sig) => {
      clearTimeout(timer);
      resolve({ code, sig });
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });

  const inputJson = JSON.stringify(input);
  child.stdin!.write(inputJson);
  child.stdin!.end();

  try {
    const { code } = await exitPromise;
    const envelope = parseEnvelope<T>(stdout, stderrLines.slice(-120));

    if (!envelope.ok && !envelope.error) {
      return {
        ok: false,
        error: makeError("E_TIMEOUT", `Worker exited with code ${code}`, {
          details: { exitCode: code, stderr_tail: stderrLines.slice(-10) },
        }),
        warnings: envelope.warnings,
      };
    }

    return envelope;
  } catch (err: unknown) {
    if (isAbortError(err)) {
      return {
        ok: false,
        error: makeError("KBPREP_CANCELLED", "Worker call was cancelled.", {
          recoverable: true,
          suggested_action: "Retry if needed.",
        }),
      };
    }
    if (isTimeoutError(err)) {
      return {
        ok: false,
        error: makeError("E_TIMEOUT", `Worker timed out after ${timeoutMs}ms`, {
          recoverable: true,
          suggested_action: "Increase timeout or check worker health.",
          details: { timeout_ms: timeoutMs, stderr_tail: stderrLines.slice(-10) },
        }),
      };
    }
    return {
      ok: false,
      error: makeError("KBPREP_INTERNAL", String(err), {
        details: { stderr_tail: stderrLines.slice(-10) },
      }),
    };
  }
}

function parseEnvelope<T>(raw: string, stderrTail: string[]): WorkerResult<T> {
  const trimmed = raw.trim();
  if (!trimmed) {
    return {
      ok: false,
      error: makeError("KBPREP_WORKER_BAD_JSON", "Worker returned empty stdout.", {
        details: { stderr_tail: stderrTail },
      }),
    };
  }
  try {
    return JSON.parse(trimmed) as WorkerResult<T>;
  } catch (err) {
    return {
      ok: false,
      error: makeError("KBPREP_WORKER_BAD_JSON", `Failed to parse worker stdout: ${err}`, {
        details: { stdout_preview: trimmed.slice(0, 500), stderr_tail: stderrTail },
      }),
    };
  }
}

interface TimeoutMarker extends Error {
  __kbprep_timeout: true;
}

function createTimeoutError(ms: number): TimeoutMarker {
  const err = new Error(`Worker timed out after ${ms}ms`) as TimeoutMarker;
  err.__kbprep_timeout = true;
  return err;
}

function isTimeoutError(err: unknown): err is TimeoutMarker {
  return err instanceof Error && "__kbprep_timeout" in err;
}

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}
