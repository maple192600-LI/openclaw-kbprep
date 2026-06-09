import { spawn } from "node:child_process";
const DEFAULT_TERMINATE_GRACE_MS = 5_000;
const TAIL_LINES = 20;
export class ManagedProcessTimeoutError extends Error {
    timeoutMs;
    code;
    signal;
    stderrTail;
    stdoutTail;
    constructor(label, timeoutMs, result) {
        const stderrTail = tailText(result.stderr ?? "");
        const stdoutTail = tailText(result.stdout ?? "");
        const evidence = stderrTail || stdoutTail;
        super([
            `Timed out while trying to ${label} after ${timeoutMs}ms`,
            `(exit ${result.code ?? "unknown"}, signal ${result.signal ?? "unknown"})`,
            evidence ? evidence : "",
        ].filter(Boolean).join(". "));
        this.name = "ManagedProcessTimeoutError";
        this.timeoutMs = timeoutMs;
        this.code = result.code;
        this.signal = result.signal;
        this.stderrTail = stderrTail;
        this.stdoutTail = stdoutTail;
    }
}
export async function runManagedProcess(options) {
    const child = spawnManagedProcess(options);
    return await collectManagedProcess(child, options);
}
function spawnManagedProcess(options) {
    const spawnOptions = {
        cwd: options.cwd,
        env: options.env,
        shell: options.shell,
        signal: options.signal,
        stdio: ["pipe", "pipe", "pipe"],
        windowsHide: true,
    };
    return spawn(options.command, options.args ?? [], spawnOptions);
}
function collectManagedProcess(child, options) {
    return new Promise((resolve, reject) => {
        let stdout = "";
        let stderr = "";
        let timedOut = false;
        let forcedKill = false;
        let settled = false;
        let terminateTimer;
        const settle = (fn) => {
            if (settled)
                return;
            settled = true;
            clearTimeout(timeoutTimer);
            if (terminateTimer)
                clearTimeout(terminateTimer);
            fn();
        };
        const timeoutTimer = setTimeout(() => {
            timedOut = true;
            child.kill("SIGTERM");
            terminateTimer = setTimeout(() => {
                forcedKill = true;
                child.kill("SIGKILL");
                settle(() => reject(new ManagedProcessTimeoutError(options.label, options.timeoutMs, {
                    code: null,
                    signal: "SIGKILL",
                    stderr,
                    stdout,
                })));
            }, options.terminateGraceMs ?? DEFAULT_TERMINATE_GRACE_MS);
        }, options.timeoutMs);
        child.stdout?.on("data", (chunk) => {
            stdout += chunk.toString("utf-8");
            options.onStdoutData?.(chunk);
        });
        child.stderr?.on("data", (chunk) => {
            stderr += chunk.toString("utf-8");
            options.onStderrData?.(chunk);
        });
        child.on("error", (err) => {
            settle(() => reject(err));
        });
        child.on("close", (code, signal) => {
            const result = {
                code,
                signal,
                stdout,
                stderr,
                timedOut,
                forcedKill,
            };
            settle(() => {
                if (timedOut) {
                    reject(new ManagedProcessTimeoutError(options.label, options.timeoutMs, result));
                    return;
                }
                resolve(result);
            });
        });
        child.stdin?.on("error", () => { });
        child.stdin?.end(options.stdin ?? "");
    });
}
function tailText(text) {
    return text.split(/\r?\n/).filter(Boolean).slice(-TAIL_LINES).join("\n");
}
