import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { callWorker, type WorkerConfig, type WorkerResult } from "../../worker.js";
import { ensurePythonRuntime, type RuntimeConfig } from "../../runtime/pythonRuntime.js";

export type StandaloneCommand =
  | "preflight"
  | "diagnose"
  | "prepare"
  | "apply_review"
  | "cleanup"
  | "prepare_batch";

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

const HELP: Record<StandaloneCommand, string> = {
  preflight: [
    "Usage: kbprep-preflight [--workdir <dir>] [--profile lite|standard] [--config-file <file>]",
    "",
    "Checks KBPrep runtime readiness without requiring OpenClaw.",
  ].join("\n"),
  diagnose: [
    "Usage: kbprep-analyze --input <file> [--output <dir>] [--source-type auto|pdf_like|markdown_note|generic_block|subtitle_transcript] [--config-file <file>]",
    "",
    "Reads one source file and reports source type, quality, and recommended processing route.",
  ].join("\n"),
  prepare: [
    "Usage: kbprep-prepare --input <file> --output <dir> [--profile lite|standard|curated_obsidian_kb] [--mode rules_only|rules_plus_review_pack] [--force] [--config-file <file>]",
    "",
    "Converts one local source file into clean Markdown and optional curated Obsidian output.",
  ].join("\n"),
  apply_review: [
    "Usage: kbprep-apply-review --run-dir <dir> --patch-file <json> [--config-file <file>]",
    "",
    "Applies a safe review JSON Patch to an existing KBPrep run.",
  ].join("\n"),
  cleanup: [
    "Usage: kbprep-cleanup --output <dir> [--action finalize|expired|all] [--older-than-days <n>] [--dry-run] [--config-file <file>]",
    "",
    "Cleans intermediate KBPrep artifacts while preserving source-side final outputs.",
  ].join("\n"),
  prepare_batch: [
    "Usage: kbprep-batch --input <dir> --output <dir> [--profile lite|standard|curated_obsidian_kb] [--mode rules_only|rules_plus_review_pack] [--convert-jobs <n>] [--config-file <file>]",
    "",
    "Processes a directory through the same Python worker used by the OpenClaw adapter.",
  ].join("\n"),
};

export function parseStandaloneArgs(argv: string[]): ParsedArgs {
  const options: Record<string, string | boolean> = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--help" || token === "-h") return { help: true, options };
    if (!token.startsWith("--")) {
      throw new Error(`Unexpected positional argument: ${token}`);
    }
    const eqIndex = token.indexOf("=");
    if (eqIndex > 2) {
      const key = normalizeKey(token.slice(2, eqIndex));
      options[key] = token.slice(eqIndex + 1);
      continue;
    }
    const key = normalizeKey(token.slice(2));
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      options[key] = true;
      continue;
    }
    options[key] = next;
    index += 1;
  }
  return { help: false, options };
}

export function buildCliPlan(command: StandaloneCommand, options: Record<string, string | boolean>): CliPlan {
  switch (command) {
    case "preflight": {
      const workspacePath = resolvePath(readString(options, "workdir") ?? process.cwd());
      mkdirSync(workspacePath, { recursive: true });
      return {
        command,
        input: {
          workspace_path: workspacePath,
          profile: readString(options, "profile") ?? "lite",
        },
        cwd: workspacePath,
        timeoutMs: 120_000,
      };
    }
    case "diagnose": {
      const outputRoot = resolvePath(readString(options, "output") ?? ".kbprep/analyze");
      mkdirSync(outputRoot, { recursive: true });
      return {
        command,
        input: {
          input_path: requirePath(options, "input"),
          output_root: outputRoot,
          source_type: readString(options, "source_type") ?? "auto",
        },
        timeoutMs: 120_000,
      };
    }
    case "prepare": {
      const outputRoot = requirePath(options, "output");
      mkdirSync(outputRoot, { recursive: true });
      return {
        command,
        input: {
          input_path: requirePath(options, "input"),
          output_root: outputRoot,
          profile: readString(options, "profile") ?? "curated_obsidian_kb",
          mode: readString(options, "mode") ?? "rules_only",
          force: readBoolean(options, "force", false),
          artifact_policy: readString(options, "artifact_policy") ?? "keep_latest",
          language: readString(options, "language") ?? "zh",
          source_type: readString(options, "source_type") ?? "auto",
          splitter: readString(options, "splitter") ?? "auto",
        },
        cwd: outputRoot,
        timeoutMs: 5_400_000,
      };
    }
    case "apply_review":
      return {
        command,
        input: {
          run_dir: requirePath(options, "run_dir"),
          patch_json: readPatchJson(options),
        },
        timeoutMs: 120_000,
      };
    case "cleanup":
      const cleanupDryRun = readBoolean(options, "dry_run", false);
      return {
        command,
        input: {
          output_root: requirePath(options, "output"),
          action: readString(options, "action") ?? (cleanupDryRun ? "all" : "finalize"),
          older_than_days: readNumber(options, "older_than_days", 7),
          confirm_review_needed: readBoolean(options, "confirm_review_needed", false),
          dry_run: cleanupDryRun,
        },
        timeoutMs: 120_000,
      };
    case "prepare_batch": {
      const outputRoot = requirePath(options, "output");
      mkdirSync(outputRoot, { recursive: true });
      return {
        command,
        input: {
          input_dir: requirePath(options, "input"),
          output_root: outputRoot,
          profile: readString(options, "profile") ?? "curated_obsidian_kb",
          mode: readString(options, "mode") ?? "rules_only",
          force: readBoolean(options, "force", false),
          artifact_policy: readString(options, "artifact_policy") ?? "keep_latest",
          language: readString(options, "language") ?? "zh",
          convert_jobs: readNumber(options, "convert_jobs", 1),
        },
        cwd: outputRoot,
        timeoutMs: 10_800_000,
      };
    }
    default:
      return assertNever(command);
  }
}

export async function runStandaloneCli(command: StandaloneCommand, argv = process.argv.slice(2)): Promise<CliRunResult> {
  try {
    const parsed = parseStandaloneArgs(argv);
    if (parsed.help) return { exitCode: 0, output: `${HELP[command]}\n` };

    const config = readRuntimeConfig(parsed.options);
    const plan = buildCliPlan(command, parsed.options);
    const pythonPath = await ensurePythonRuntime(config);
    const result = await callWorker(plan.command, plan.input, {
      pythonPath,
      cwd: plan.cwd,
      timeoutMs: plan.timeoutMs,
      config: workerConfig(config),
    });
    return formatResult(result);
  } catch (error) {
    return {
      exitCode: 1,
      output: `${JSON.stringify({
        ok: false,
        error: {
          code: "KBPREP_CLI_ERROR",
          message: error instanceof Error ? error.message : String(error),
        },
      }, null, 2)}\n`,
    };
  }
}

export async function main(command: StandaloneCommand, argv = process.argv.slice(2)): Promise<void> {
  const result = await runStandaloneCli(command, argv);
  process.stdout.write(result.output);
  process.exitCode = result.exitCode;
}

function readRuntimeConfig(options: Record<string, string | boolean>): RuntimeConfig {
  const configPath = readString(options, "config_file");
  const fileConfig = configPath
    ? JSON.parse(readFileSync(resolvePath(configPath), "utf-8")) as Record<string, unknown>
    : {};
  return {
    device_override: readDeviceOverride(options, fileConfig),
    max_cpu_threads: readNumber(options, "max_cpu_threads", readOptionalNumber(fileConfig.max_cpu_threads)),
    min_free_memory_gb: readNumber(options, "min_free_memory_gb", readOptionalNumber(fileConfig.min_free_memory_gb)),
    mineru_timeout_seconds: readNumber(options, "mineru_timeout_seconds", readOptionalNumber(fileConfig.mineru_timeout_seconds)),
    python_path: readString(options, "python_path") ?? readOptionalString(fileConfig.python_path),
  };
}

function workerConfig(config: RuntimeConfig): WorkerConfig {
  return {
    device_override: config.device_override,
    max_cpu_threads: config.max_cpu_threads,
    min_free_memory_gb: config.min_free_memory_gb,
    mineru_timeout_seconds: config.mineru_timeout_seconds,
  };
}

function formatResult(result: WorkerResult): CliRunResult {
  return {
    exitCode: result.ok ? 0 : 1,
    output: `${JSON.stringify(result, null, 2)}\n`,
  };
}

function readPatchJson(options: Record<string, string | boolean>): unknown {
  const inline = readString(options, "patch_json");
  if (inline) return JSON.parse(inline);
  const patchFile = readString(options, "patch_file");
  if (patchFile) return JSON.parse(readFileSync(resolvePath(patchFile), "utf-8"));
  throw new Error("--patch-file or --patch-json is required.");
}

function readDeviceOverride(options: Record<string, string | boolean>, fileConfig: Record<string, unknown>): RuntimeConfig["device_override"] {
  const raw = readString(options, "device_override") ?? readOptionalString(fileConfig.device_override);
  if (!raw) return undefined;
  if (raw === "auto" || raw === "cuda" || raw === "cpu") return raw;
  throw new Error(`Invalid device_override: ${raw}`);
}

function requirePath(options: Record<string, string | boolean>, key: string): string {
  const value = readString(options, key);
  if (!value) throw new Error(`--${key.replace(/_/g, "-")} is required.`);
  return resolvePath(value);
}

function resolvePath(value: string): string {
  return resolve(process.cwd(), value);
}

function readString(options: Record<string, string | boolean>, key: string): string | undefined {
  const value = options[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function readOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function readNumber(options: Record<string, string | boolean>, key: string, fallback: number | undefined): number | undefined {
  const raw = readString(options, key);
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`--${key.replace(/_/g, "-")} must be a number.`);
  return value;
}

function readOptionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function readBoolean(options: Record<string, string | boolean>, key: string, fallback: boolean): boolean {
  const value = options[key];
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (value === "true") return true;
    if (value === "false") return false;
    throw new Error(`--${key.replace(/_/g, "-")} must be true or false.`);
  }
  return fallback;
}

function normalizeKey(key: string): string {
  return key.replace(/-/g, "_");
}

function assertNever(value: never): never {
  throw new Error(`Unhandled command: ${value}`);
}
