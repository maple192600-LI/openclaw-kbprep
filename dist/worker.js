/**
 * Python worker spawner for kbprep.
 * Uses child_process.spawn to call Python CLI.
 * No HTTP service, no daemon, no persistent worker.
 */
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, appendFile } from "node:fs/promises";
import { delimiter, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { makeError } from "./errors.js";
async function writeStdin(stream, input) {
    await new Promise((resolve, reject) => {
        const cleanup = () => {
            stream.off("error", onError);
            stream.off("drain", onDrain);
        };
        const finish = () => {
            cleanup();
            stream.end(() => resolve());
        };
        const onError = (err) => {
            cleanup();
            reject(err);
        };
        const onDrain = () => {
            finish();
        };
        stream.once("error", onError);
        try {
            if (stream.write(input)) {
                finish();
                return;
            }
        }
        catch (err) {
            onError(err instanceof Error ? err : new Error(String(err)));
            return;
        }
        stream.once("drain", onDrain);
    });
}
/**
 * Call Python worker via CLI mode.
 * stdout: single JSON envelope
 * stderr: JSONL logs
 */
export async function callWorker(command, input, options) {
    const { pythonPath, cwd, timeoutMs, signal, logDir } = options;
    const jobId = randomUUID().replace(/-/g, "").slice(0, 16);
    const args = ["-m", "kbprep_worker.cli", command, "--json-stdin"];
    const env = { ...process.env };
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
    // Pass worker runtime config as environment variables.
    if (options.config?.device_override) {
        env.MINERU_DEVICE_MODE = options.config.device_override;
    }
    if (options.config?.max_cpu_threads) {
        env.TORCH_NUM_THREADS = String(options.config.max_cpu_threads);
        env.OMP_NUM_THREADS = String(options.config.max_cpu_threads);
    }
    if (options.config?.mineru_timeout_seconds) {
        env.KBPREP_MINERU_TIMEOUT_SECONDS = String(options.config.mineru_timeout_seconds);
    }
    const child = spawn(pythonPath, args, {
        cwd,
        stdio: ["pipe", "pipe", "pipe"],
        signal,
        windowsHide: true,
        env,
    });
    let stdout = "";
    child.stdout.on("data", (chunk) => {
        stdout += chunk.toString("utf-8");
    });
    let stderr = "";
    const stderrLines = [];
    child.stderr.on("data", (chunk) => {
        const text = chunk.toString("utf-8");
        stderr += text;
        for (const line of text.split("\n")) {
            const trimmed = line.trim();
            if (trimmed)
                stderrLines.push(trimmed);
        }
    });
    // Write stderr JSONL to log file if logDir specified
    if (logDir) {
        await mkdir(logDir, { recursive: true });
        const logPath = join(logDir, `${jobId}.jsonl`);
        child.stderr.on("data", async (chunk) => {
            try {
                await appendFile(logPath, chunk);
            }
            catch { }
        });
    }
    const exitPromise = new Promise((resolve, reject) => {
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
    try {
        const inputJson = JSON.stringify(input);
        await writeStdin(child.stdin, inputJson);
        const { code } = await exitPromise;
        const envelope = parseEnvelope(stdout, stderrLines.slice(-120));
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
    }
    catch (err) {
        if (isAbortError(err)) {
            return {
                ok: false,
                error: makeError("E_CANCELLED", "Worker call was cancelled.", {
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
            error: makeError("E_INTERNAL", String(err), {
                details: { stderr_tail: stderrLines.slice(-10) },
            }),
        };
    }
}
function parseEnvelope(raw, stderrTail) {
    const trimmed = raw.trim();
    if (!trimmed) {
        return {
            ok: false,
            error: makeError("E_WORKER_BAD_JSON", "Worker returned empty stdout.", {
                details: { stderr_tail: stderrTail },
            }),
        };
    }
    try {
        return JSON.parse(trimmed);
    }
    catch (err) {
        return {
            ok: false,
            error: makeError("E_WORKER_BAD_JSON", `Failed to parse worker stdout: ${err}`, {
                details: { stdout_preview: trimmed.slice(0, 500), stderr_tail: stderrTail },
            }),
        };
    }
}
function createTimeoutError(ms) {
    const err = new Error(`Worker timed out after ${ms}ms`);
    err.__kbprep_timeout = true;
    return err;
}
function isTimeoutError(err) {
    return err instanceof Error && "__kbprep_timeout" in err;
}
function isAbortError(err) {
    return err instanceof Error && err.name === "AbortError";
}
