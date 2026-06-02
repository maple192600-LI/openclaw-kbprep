import { type KBPrepError } from "./errors.js";
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
export declare function callWorker<T = Record<string, unknown>>(command: string, input: Record<string, unknown>, options: WorkerCallOptions): Promise<WorkerResult<T>>;
