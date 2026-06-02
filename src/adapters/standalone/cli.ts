/**
 * Standalone CLI adapter: lets users run kbprep from any shell, with no
 * host agent runtime required. Useful for:
 *   - System administrators running kbprep from cron
 *   - Self-media operators running kbprep from a Makefile / shell script
 *   - Any agent that can spawn a subprocess and parse JSON
 *
 * Bin (added to package.json [bin]):
 *     kbprep-convert     - single-file convert + clean
 *     kbprep-analyze     - diagnose
 *     kbprep-preflight   - readiness check
 *     kbprep-batch       - batch convert
 *     kbprep-cleanup     - cleanup artifacts
 *     kbprep-mcp         - start the MCP server (also exposed separately)
 *
 * All commands read JSON config from --config-file <path> (or `-` for stdin)
 * and write the worker's JSON envelope to stdout, mirroring the Python CLI.
 */
import { ensurePythonRuntime } from "../python_runtime.js";
import { callWorker, type WorkerConfig } from "../../worker.js";

interface CliOptions {
  configFile?: string;
  workdir?: string;
  inputPath?: string;
  outputRoot?: string;
  mode?: "rules_only" | "rules_plus_review_pack" | "ai_review";
  artifactPolicy?: "keep_latest" | "keep_all" | "final_only";
  action?: "finalize" | "expired" | "all";
  olderThanDays?: number;
  sampleFirst?: boolean;
  deviceOverride?: "auto" | "cuda" | "cpu";
  maxCpuThreads?: number;
  json: boolean;
}

export async function runCli(tool: string, opts: CliOptions): Promise<number> {
  const pythonPath = await ensurePythonRuntime();
  const cfg = await loadConfig(opts);

  const command = toolToCommand(tool);
  if (!command) {
    process.stderr.write(`Unknown tool: ${tool}\n`);
    return 2;
  }
  const input = buildInput(tool, opts, cfg);
  const workerConfig: WorkerConfig = {
    device_override: opts.deviceOverride ?? cfg.device_override ?? "auto",
    max_cpu_threads: opts.maxCpuThreads ?? cfg.max_cpu_threads,
    min_free_memory_gb: cfg.min_free_memory_gb,
    mineru_timeout_seconds: cfg.mineru_timeout_seconds,
  };

  const result = await callWorker(command, input, {
    pythonPath,
    timeoutMs: timeoutFor(tool),
    config: workerConfig,
  });

  process.stdout.write(JSON.stringify(result, null, opts.json ? 2 : 0) + "\n");
  return result.ok ? 0 : 1;
}

function toolToCommand(tool: string): string | null {
  switch (tool) {
    case "kbprep_preflight":
      return "preflight";
    case "kbprep_analyze":
      return "diagnose";
    case "kbprep_prepare":
      return "prepare";
    case "kbprep_apply_review":
      return "apply-review";
    case "kbprep_cleanup":
      return "cleanup";
    case "kbprep_prepare_batch":
      return "prepare-batch";
    default:
      return null;
  }
}

function timeoutFor(tool: string): number {
  switch (tool) {
    case "kbprep_preflight":
      return 30_000;
    case "kbprep_analyze":
      return 60_000;
    case "kbprep_apply_review":
      return 60_000;
    case "kbprep_cleanup":
      return 30_000;
    case "kbprep_prepare":
    case "kbprep_prepare_batch":
      return 60 * 60_000;
    default:
      return 60_000;
  }
}

function buildInput(tool: string, opts: CliOptions, cfg: Record<string, unknown>): Record<string, unknown> {
  switch (tool) {
    case "kbprep_preflight":
      return { workdir: opts.workdir, config: cfg };
    case "kbprep_analyze":
      return { input_path: opts.inputPath, workdir: opts.workdir, config: cfg };
    case "kbprep_prepare":
      return {
        input_path: opts.inputPath,
        output_root: opts.outputRoot,
        mode: opts.mode ?? "rules_only",
        artifact_policy: opts.artifactPolicy ?? "keep_latest",
        config: cfg,
      };
    case "kbprep_apply_review": {
      const patchJson = cfg.patch_json ?? [];
      return { run_dir: opts.workdir, patch_json: patchJson };
    }
    case "kbprep_cleanup":
      return {
        output_root: opts.outputRoot,
        action: opts.action ?? "expired",
        older_than_days: opts.olderThanDays ?? 7,
        confirm_review_needed: cfg.confirm_review_needed ?? false,
      };
    case "kbprep_prepare_batch":
      return {
        input_root: opts.inputPath,
        output_root: opts.outputRoot,
        mode: opts.mode ?? "rules_only",
        sample_first: opts.sampleFirst ?? true,
        config: cfg,
      };
    default:
      return {};
  }
}

async function loadConfig(opts: CliOptions): Promise<Record<string, unknown>> {
  if (!opts.configFile) return {};
  const fs = await import("node:fs/promises");
  const raw = opts.configFile === "-" ? await readAllStdin() : await fs.readFile(opts.configFile, "utf-8");
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch (err) {
    process.stderr.write(`Failed to parse --config-file: ${String(err)}\n`);
    return {};
  }
}

async function readAllStdin(): Promise<string> {
  return new Promise((resolve) => {
    let buf = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (c: string) => (buf += c));
    process.stdin.on("end", () => resolve(buf));
  });
}

/** Lightweight arg parser for `bin/kbprep-*` scripts. */
export function parseArgs(argv: string[]): { tool: string; opts: CliOptions } {
  const tool = argv[0];
  const opts: CliOptions = { json: true };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    switch (arg) {
      case "--config-file":
        opts.configFile = next;
        i += 1;
        break;
      case "--workdir":
        opts.workdir = next;
        i += 1;
        break;
      case "--input":
        opts.inputPath = next;
        i += 1;
        break;
      case "--output":
        opts.outputRoot = next;
        i += 1;
        break;
      case "--mode":
        opts.mode = next as CliOptions["mode"];
        i += 1;
        break;
      case "--artifact-policy":
        opts.artifactPolicy = next as CliOptions["artifactPolicy"];
        i += 1;
        break;
      case "--action":
        opts.action = next as CliOptions["action"];
        i += 1;
        break;
      case "--older-than-days":
        opts.olderThanDays = Number(next);
        i += 1;
        break;
      case "--sample-first":
        opts.sampleFirst = next !== "false";
        i += 1;
        break;
      case "--device-override":
        opts.deviceOverride = next as CliOptions["deviceOverride"];
        i += 1;
        break;
      case "--max-cpu-threads":
        opts.maxCpuThreads = Number(next);
        i += 1;
        break;
      case "--no-pretty":
        opts.json = false;
        break;
      case "--help":
      case "-h":
        process.stdout.write(HELP[tool] ?? `Unknown tool: ${tool}\n`);
        process.exit(0);
        break;
      default:
        process.stderr.write(`Unknown flag: ${arg}\n`);
    }
  }
  return { tool, opts };
}

const HELP: Record<string, string> = {
  kbprep_preflight:
    "Usage: kbprep-preflight [--workdir DIR] [--config-file FILE]\n" +
    "  Read-only runtime readiness check (Python, MinerU, GPU/CPU, memory, disk).",
  kbprep_analyze:
    "Usage: kbprep-analyze --input FILE [--workdir DIR] [--config-file FILE]\n" +
    "  Read-only file-type diagnosis.",
  kbprep_prepare:
    "Usage: kbprep-prepare --input FILE --output DIR [--mode MODE] [--artifact-policy POLICY] [--config-file FILE]\n" +
    "  Single-file convert + clean. Modes: rules_only | rules_plus_review_pack | ai_review.",
  kbprep_apply_review:
    "Usage: kbprep-apply-review --workdir RUN_DIR [--config-file FILE]\n" +
    "  Apply a JSON Patch 1.0 array from --config-file.patch_json.",
  kbprep_cleanup:
    "Usage: kbprep-cleanup --output DIR [--action ACTION] [--older-than-days N] [--config-file FILE]\n" +
    "  Cleanup artifacts. Actions: finalize | expired | all.",
  kbprep_prepare_batch:
    "Usage: kbprep-batch --input DIR --output DIR [--mode MODE] [--sample-first BOOL] [--config-file FILE]\n" +
    "  Batch convert. sample-first defaults to true; flips off only on explicit --sample-first false.",
};
