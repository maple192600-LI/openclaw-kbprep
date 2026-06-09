export type StandaloneCommand = "preflight" | "diagnose" | "prepare" | "apply_review" | "feedback" | "cleanup" | "prepare_batch";
type ParsedArgs = {
    help: boolean;
    options: Record<string, string | boolean>;
};
type CliPlan = {
    command: StandaloneCommand;
    input: Record<string, unknown>;
    cwd?: string;
    timeoutMs: number;
};
type CliRunResult = {
    exitCode: number;
    output: string;
};
export declare function parseStandaloneArgs(argv: string[]): ParsedArgs;
export declare function buildCliPlan(command: StandaloneCommand, options: Record<string, string | boolean>): CliPlan;
export declare function runStandaloneCli(command: StandaloneCommand, argv?: string[]): Promise<CliRunResult>;
export declare function main(command: StandaloneCommand, argv?: string[]): Promise<void>;
export {};
