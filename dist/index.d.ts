export declare function resolvePythonPath(startPath: string, config?: PluginConfig): string;
export declare function ensurePythonRuntime(config?: PluginConfig): Promise<string>;
export declare function pluginVenvPythonPath(): string;
type PluginConfig = {
    device_override?: "auto" | "cuda" | "cpu";
    max_cpu_threads?: number;
    min_free_memory_gb?: number;
    mineru_timeout_seconds?: number;
    python_path?: string;
    ai_review_provider?: string;
    ai_review_model?: string;
};
declare const _default: import("openclaw/plugin-sdk/tool-plugin").DefinedToolPluginEntry;
export default _default;
