export type RuntimeConfig = {
    device_override?: "cuda" | "cpu";
    max_cpu_threads?: number;
    min_free_memory_gb?: number;
    mineru_timeout_seconds?: number;
    python_path?: string;
};
export type RuntimeSetupStepId = "create_venv" | "upgrade_packaging" | "install_worker" | "probe_environment";
export type RuntimeSetupStep = {
    id: RuntimeSetupStepId;
    label: string;
    timeoutMs: number;
};
export type RuntimeSetupProgressEvent = {
    type: "step_start" | "step_success";
    step: RuntimeSetupStep;
};
export type RuntimeSetupProgress = (event: RuntimeSetupProgressEvent) => void;
export declare function resolvePythonPath(_startPath?: string, config?: RuntimeConfig): string;
export declare function ensurePythonRuntime(config?: RuntimeConfig, onProgress?: RuntimeSetupProgress): Promise<string>;
export declare function runtimeSetupStepsForTest(): RuntimeSetupStep[];
export declare function runSetupCommandForTest(command: string, args: string[], label: string, timeoutMs: number, stdin?: string): Promise<{
    stdout: string;
    stderr: string;
}>;
export declare function kbprepVenvPythonPath(): string;
export declare function isRuntimeMarkerCurrent(marker: unknown, config?: RuntimeConfig): boolean;
