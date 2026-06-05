export type RuntimeConfig = {
    device_override?: "cuda" | "cpu";
    max_cpu_threads?: number;
    min_free_memory_gb?: number;
    mineru_timeout_seconds?: number;
    python_path?: string;
};
export declare function resolvePythonPath(_startPath?: string, config?: RuntimeConfig): string;
export declare function ensurePythonRuntime(config?: RuntimeConfig): Promise<string>;
export declare function pluginVenvPythonPath(): string;
export declare const kbprepVenvPythonPath: typeof pluginVenvPythonPath;
export declare function isRuntimeMarkerCurrent(marker: unknown, config?: RuntimeConfig): boolean;
