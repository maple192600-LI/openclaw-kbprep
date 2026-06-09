export type ManagedProcessResult = {
    code: number | null;
    signal: NodeJS.Signals | null;
    stdout: string;
    stderr: string;
    timedOut: boolean;
    forcedKill: boolean;
};
export type ManagedProcessOptions = {
    command: string;
    args?: string[];
    label: string;
    timeoutMs: number;
    terminateGraceMs?: number;
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    shell?: boolean;
    stdin?: string;
    signal?: AbortSignal;
    onStdoutData?: (chunk: Buffer) => void;
    onStderrData?: (chunk: Buffer) => void;
};
export declare class ManagedProcessTimeoutError extends Error {
    readonly timeoutMs: number;
    readonly code: number | null;
    readonly signal: NodeJS.Signals | null;
    readonly stderrTail: string;
    readonly stdoutTail: string;
    constructor(label: string, timeoutMs: number, result: Pick<ManagedProcessResult, "code" | "signal"> & Partial<Pick<ManagedProcessResult, "stderr" | "stdout">>);
}
export declare function runManagedProcess(options: ManagedProcessOptions): Promise<ManagedProcessResult>;
