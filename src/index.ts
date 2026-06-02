import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";
import { callWorker } from "./worker.js";
import { maybeRunAiReview } from "./aiReview.js";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RUNTIME_MARKER_SCHEMA = "kbprep.plugin_venv.v2";
const PYTHON_WORKER_DEPENDENCY_SPEC = "mineru[all]==3.2.1;PyMuPDF==1.27.2.3;beautifulsoup4==4.14.3;lxml==6.0.2";

export function resolvePythonPath(startPath: string, config?: PluginConfig): string {
  const pluginPython = pluginVenvPythonPath();
  if (isPluginVenvReady(config)) return pluginPython;

  if (shouldSkipAutoSetupForTests()) {
    if (config?.python_path?.trim()) return config.python_path.trim();

    return process.env.KBPREP_PYTHON
      ?? process.env.PYTHON
      ?? (process.platform === "win32" ? "python" : "python3");
  }

  return pluginPython;
}

export async function ensurePythonRuntime(config?: PluginConfig): Promise<string> {
  const pythonPath = pluginVenvPythonPath();
  if (isPluginVenvReady(config)) return pythonPath;

  if (shouldSkipAutoSetupForTests()) return resolvePythonPath(pluginRootDir(), config);

  const venvDir = pluginVenvDir();
  cleanupStalePluginRuntime(config);
  mkdirSync(dirname(venvDir), { recursive: true });
  const bootstrap = bootstrapPythonCommand(config);
  await runSetupCommand(
    bootstrap.command,
    [...bootstrap.args, "-m", "venv", venvDir],
    "create plugin-local Python virtual environment",
    5 * 60_000,
  );
  await runSetupCommand(
    pythonPath,
    ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
    "upgrade pip in plugin-local Python virtual environment",
    10 * 60_000,
  );
  await runSetupCommand(
    pythonPath,
    ["-m", "pip", "install", "-e", pluginPythonProjectDir()],
    "install kbprep worker dependencies into plugin-local Python virtual environment",
    60 * 60_000,
  );
  const setupResult = await runSetupCommand(
    pythonPath,
    ["-m", "kbprep_worker.cli", "setup-env", "--json-stdin"],
    "detect hardware and tune plugin-local Python dependencies",
    30 * 60_000,
    JSON.stringify({ device_override: config?.device_override ?? "auto" }),
  );
  writeFileSync(pluginVenvReadyMarker(), JSON.stringify({
    schema: RUNTIME_MARKER_SCHEMA,
    created_at: new Date().toISOString(),
    plugin_version: pluginPackageVersion(),
    python_executable: pythonPath,
    device_override: effectiveDeviceOverride(config),
    python_project: {
      path: pluginPythonProjectDir(),
      dependency_spec: PYTHON_WORKER_DEPENDENCY_SPEC,
    },
    setup_env: parseSetupEnvelope(setupResult.stdout),
  }, null, 2), "utf-8");
  return pythonPath;
}

function pluginRootDir(): string {
  const moduleDir = dirname(fileURLToPath(import.meta.url));
  if (basename(moduleDir) === "dist" || basename(moduleDir) === "src") {
    return resolve(moduleDir, "..");
  }
  return moduleDir;
}

function pluginPythonProjectDir(): string {
  return join(pluginRootDir(), "python");
}

function pluginVenvDir(): string {
  return join(pluginRootDir(), ".kbprep", "venv");
}

function pluginVenvReadyMarker(): string {
  return join(pluginRootDir(), ".kbprep", "runtime-ready.json");
}

function isPluginVenvReady(config?: PluginConfig): boolean {
  if (!existsSync(pluginVenvPythonPath()) || !existsSync(pluginVenvReadyMarker())) {
    return false;
  }
  return isRuntimeMarkerCurrent(readRuntimeMarker(), config);
}

export function pluginVenvPythonPath(): string {
  const venvDir = pluginVenvDir();
  return process.platform === "win32"
    ? join(venvDir, "Scripts", "python.exe")
    : join(venvDir, "bin", "python");
}

function shouldSkipAutoSetupForTests(): boolean {
  return process.env.VITEST === "true" || process.env.KBPREP_SKIP_AUTO_SETUP === "1";
}

function cleanupStalePluginRuntime(config?: PluginConfig): void {
  if (!existsSync(pluginVenvDir()) && !existsSync(pluginVenvReadyMarker())) return;
  if (isPluginVenvReady(config)) return;
  rmSync(pluginVenvDir(), { recursive: true, force: true });
  rmSync(pluginVenvReadyMarker(), { force: true });
}

function readRuntimeMarker(): unknown {
  try {
    return JSON.parse(readFileSync(pluginVenvReadyMarker(), "utf-8"));
  } catch {
    return null;
  }
}

export function isRuntimeMarkerCurrent(marker: unknown, config?: PluginConfig): boolean {
  if (!marker || typeof marker !== "object") return false;
  const data = marker as Record<string, unknown>;
  const pythonProject = data.python_project as Record<string, unknown> | undefined;
  const setupEnv = data.setup_env as Record<string, unknown> | undefined;
  const setupData = setupEnv?.data as Record<string, unknown> | undefined;

  return (
    data.schema === RUNTIME_MARKER_SCHEMA
    && data.plugin_version === pluginPackageVersion()
    && data.python_executable === pluginVenvPythonPath()
    && data.device_override === effectiveDeviceOverride(config)
    && pythonProject?.dependency_spec === PYTHON_WORKER_DEPENDENCY_SPEC
    && setupEnv?.ok === true
    && !hasCudaSetupFailure(setupData)
  );
}

function hasCudaSetupFailure(setupData?: Record<string, unknown>): boolean {
  const actions = setupData?.actions_taken;
  if (!Array.isArray(actions)) return false;
  return actions.some((action) => typeof action === "string" && action.startsWith("cuda_install_failed"));
}

function effectiveDeviceOverride(config?: PluginConfig): "auto" | "cuda" | "cpu" {
  return config?.device_override ?? "auto";
}

function pluginPackageVersion(): string {
  try {
    const pkg = JSON.parse(readFileSync(join(pluginRootDir(), "package.json"), "utf-8"));
    return String(pkg.version || "unknown");
  } catch {
    return "unknown";
  }
}

function bootstrapPythonCommand(config?: PluginConfig): { command: string; args: string[] } {
  if (config?.python_path?.trim()) return { command: config.python_path.trim(), args: [] };
  const envBootstrap = process.env.KBPREP_BOOTSTRAP_PYTHON?.trim();
  if (envBootstrap) return { command: envBootstrap, args: [] };
  if (process.platform === "win32") return { command: "py", args: ["-3"] };
  return { command: "python3", args: [] };
}

function runSetupCommand(
  command: string,
  args: string[],
  label: string,
  timeoutMs: number,
  stdin = "",
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd: pluginRootDir(),
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      env: {
        ...process.env,
        PIP_DISABLE_PIP_VERSION_CHECK: "1",
        PYTHONUTF8: "1",
        PYTHONIOENCODING: "utf-8",
      },
    });
    let stderr = "";
    let stdout = "";
    child.stdout?.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });
    if (stdin) child.stdin?.end(stdin);
    else child.stdin?.end();
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`Timed out while trying to ${label}`));
    }, timeoutMs);
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) {
        resolvePromise({ stdout, stderr });
        return;
      }
      const tail = (stderr || stdout).split(/\r?\n/).filter(Boolean).slice(-20).join("\n");
      reject(new Error(`Failed to ${label} (exit ${code}). ${tail}`));
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

function parseSetupEnvelope(stdout: string): unknown {
  const trimmed = stdout.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return { raw_stdout_preview: trimmed.slice(0, 500) };
  }
}

const sourceTypeSchema = Type.Union([
  Type.Literal("auto"),
  Type.Literal("pdf_like"),
  Type.Literal("markdown_note"),
  Type.Literal("generic_block"),
  Type.Literal("subtitle_transcript"),
], { description: "Source type override. Default 'auto'." });

const configSchema = Type.Object({
  device_override: Type.Optional(
    Type.Union([Type.Literal("auto"), Type.Literal("cuda"), Type.Literal("cpu")], {
      description: "Force device mode. Default 'auto' (detect).",
    })
  ),
  max_cpu_threads: Type.Optional(
    Type.Number({ description: "Max CPU threads for CPU-mode inference. Default 4.", default: 4 })
  ),
  min_free_memory_gb: Type.Optional(
    Type.Number({ description: "Min free memory GB before batch pauses. Default 4.", default: 4 })
  ),
  mineru_timeout_seconds: Type.Optional(
    Type.Number({
      description: "Timeout in seconds for a single MinerU conversion subprocess. Default 1140.",
      default: 1140,
    })
  ),
  python_path: Type.Optional(
    Type.String({
      description:
        "Optional absolute path to a base Python executable used only to create the plugin-local .kbprep/venv runtime.",
    })
  ),
  ai_review_provider: Type.Optional(
    Type.String({ description: "Optional provider override for mode='ai_review'." })
  ),
  ai_review_model: Type.Optional(
    Type.String({ description: "Optional model override for mode='ai_review'." })
  ),
}, { additionalProperties: false });

type PluginConfig = {
  device_override?: "auto" | "cuda" | "cpu";
  max_cpu_threads?: number;
  min_free_memory_gb?: number;
  mineru_timeout_seconds?: number;
  python_path?: string;
  ai_review_provider?: string;
  ai_review_model?: string;
};

function workerConfig(config: PluginConfig) {
  return {
    device_override: config.device_override,
    max_cpu_threads: config.max_cpu_threads,
    min_free_memory_gb: config.min_free_memory_gb,
    mineru_timeout_seconds: config.mineru_timeout_seconds,
  };
}

function ensureDirectory(path: string): void {
  mkdirSync(path, { recursive: true });
}

export default defineToolPlugin({
  id: "openclaw-kbprep",
  name: "KB Prep Tool",
  description:
    "Convert raw local files into clean Markdown for Obsidian or LLM Wiki use. It defaults to curated Obsidian knowledge-base output; use standard only for broad cleaned Markdown.",
  configSchema,
  tools: (tool) => [
    tool({
      name: "kbprep_preflight",
      label: "KBPrep Preflight",
      description:
        "Check local runtime readiness before conversion: Python, MinerU, device mode, model cache, memory, disk space, and workspace write permissions.",
      parameters: Type.Object({
        workspace_path: Type.String({ description: "Absolute path to a writable workspace or kbprep output root." }),
        profile: Type.Optional(
          Type.Union([Type.Literal("lite"), Type.Literal("standard")], {
            description: "Resource profile for readiness checks. Default 'lite'.",
          })
        ),
      }),
      async execute({ workspace_path, profile }, config, ctx) {
        ensureDirectory(workspace_path);
        const pythonPath = await ensurePythonRuntime(config);
        return callWorker("preflight", {
          workspace_path,
          profile: profile ?? "lite",
        }, {
          pythonPath,
          cwd: workspace_path,
          timeoutMs: 120_000,
          signal: ctx.signal,
          config: workerConfig(config),
        });
      },
    }),

    tool({
      name: "kbprep_analyze",
      label: "KBPrep Analyze",
      description:
        "Detect local source type and quality: file hash, format, PDF subtype, text profile, OCR recommendation, and safe processing route. Read-only.",
      parameters: Type.Object({
        input_path: Type.String({ description: "Absolute path to the source file." }),
        output_root: Type.String({ description: "Absolute path to kbprep output root." }),
        source_type: Type.Optional(sourceTypeSchema),
      }),
      async execute({ input_path, output_root, source_type }, config, ctx) {
        ensureDirectory(output_root);
        const pythonPath = await ensurePythonRuntime(config);
        return callWorker("diagnose", {
          input_path,
          output_root,
          source_type: source_type ?? "auto",
        }, {
          pythonPath,
          timeoutMs: 120_000,
          signal: ctx.signal,
          config: workerConfig(config),
        });
      },
    }),

    tool({
      name: "kbprep_prepare",
      label: "KBPrep Prepare",
      description:
        "Convert one local source file into clean Markdown: detect, preserve original, convert, normalize, blockify, clean, optionally curate into an Obsidian wiki folder, render, split, and quality check.",
      parameters: Type.Object({
        input_path: Type.String({ description: "Absolute path to the source file." }),
        output_root: Type.String({ description: "Absolute path to kbprep output root." }),
        profile: Type.Optional(
          Type.Union([Type.Literal("lite"), Type.Literal("standard"), Type.Literal("curated_obsidian_kb")], {
            description: "Resource/output profile. Default 'curated_obsidian_kb' for text-first Obsidian wiki outputs with author/marketing wrappers removed. Use 'standard' only when you explicitly want a broad cleaned Markdown file.",
          })
        ),
        mode: Type.Optional(
          Type.Union([Type.Literal("rules_only"), Type.Literal("rules_plus_review_pack"), Type.Literal("ai_review")], {
            description: "Processing mode. Default 'rules_only'.",
          })
        ),
        force: Type.Optional(Type.Boolean({ description: "Force re-process even if same hash+config. Default false." })),
        artifact_policy: Type.Optional(
          Type.Union([Type.Literal("keep_latest"), Type.Literal("keep_all"), Type.Literal("final_only")], {
            description: "Intermediate artifact retention. Default 'keep_latest' keeps the latest successful outputs and prunes old runs.",
          })
        ),
        language: Type.Optional(Type.String({ description: "Language hint. Default 'zh'." })),
        source_type: Type.Optional(sourceTypeSchema),
        splitter: Type.Optional(sourceTypeSchema),
        ai_review_provider: Type.Optional(Type.String({ description: "Optional provider override for mode='ai_review'." })),
        ai_review_model: Type.Optional(Type.String({ description: "Optional model override for mode='ai_review'." })),
      }),
      async execute(params, config, ctx) {
        ensureDirectory(params.output_root);
        const pythonPath = await ensurePythonRuntime(config);
        const effectiveMode = params.mode ?? "rules_only";
        const workerMode = effectiveMode === "ai_review" ? "rules_plus_review_pack" : effectiveMode;
        const workerCfg = workerConfig(config);
        const result = await callWorker("prepare", {
          input_path: params.input_path,
          output_root: params.output_root,
          profile: params.profile ?? "curated_obsidian_kb",
          mode: workerMode,
          force: params.force ?? false,
          artifact_policy: params.artifact_policy ?? "keep_latest",
          language: params.language ?? "zh",
          source_type: params.source_type ?? "auto",
          splitter: params.splitter ?? "auto",
        }, {
          pythonPath,
          cwd: params.output_root,
          timeoutMs: 5_400_000,
          signal: ctx.signal,
          logDir: `${params.output_root}/.kbprep/logs`,
          config: workerCfg,
        });

        return maybeRunAiReview(result, {
          mode: effectiveMode,
          ai_review_provider: params.ai_review_provider,
          ai_review_model: params.ai_review_model,
        }, config, ctx, {
          pythonPath,
          timeoutMs: 900_000,
          workerConfig: workerCfg,
        });
      },
    }),

    tool({
      name: "kbprep_apply_review",
      label: "KBPrep Apply Review",
      description:
        "Apply an RFC 6902 JSON Patch from AI or human review. Only block status metadata can change; source text cannot be rewritten.",
      parameters: Type.Object({
        run_dir: Type.String({ description: "Absolute path to the run directory." }),
        patch_json: Type.Array(Type.Any(), { description: "RFC 6902 JSON Patch operations array." }),
      }),
      async execute({ run_dir, patch_json }, config, ctx) {
        const pythonPath = await ensurePythonRuntime(config);
        return callWorker("apply_review", {
          run_dir,
          patch_json,
        }, {
          pythonPath,
          timeoutMs: 120_000,
          signal: ctx.signal,
          config: workerConfig(config),
        });
      },
    }),

    tool({
      name: "kbprep_cleanup",
      label: "KBPrep Cleanup",
      description:
        "Clean kbprep intermediate artifacts after a successful conversion. It never deletes the source file or the source-side final Markdown.",
      parameters: Type.Object({
        output_root: Type.String({ description: "Absolute path to the kbprep output root to clean." }),
        action: Type.Optional(
          Type.Union([Type.Literal("finalize"), Type.Literal("expired"), Type.Literal("all")], {
            description:
              "Cleanup action. 'finalize' keeps only source-side deliverables plus a tiny manifest; 'expired' removes old run history; 'all' removes known intermediate artifacts.",
          })
        ),
        older_than_days: Type.Optional(Type.Number({ description: "For action='expired', delete run history older than this many days. Default 7." })),
        confirm_review_needed: Type.Optional(
          Type.Boolean({
            description:
              "Allow finalize even when review_needed.md still has content. Default false.",
          })
        ),
        dry_run: Type.Optional(Type.Boolean({ description: "Preview what would be deleted without deleting files. Default false." })),
      }),
      async execute(params, config, ctx) {
        const pythonPath = await ensurePythonRuntime(config);
        return callWorker("cleanup", {
          output_root: params.output_root,
          action: params.action ?? "finalize",
          older_than_days: params.older_than_days ?? 7,
          confirm_review_needed: params.confirm_review_needed ?? false,
          dry_run: params.dry_run ?? false,
        }, {
          pythonPath,
          timeoutMs: 120_000,
          signal: ctx.signal,
          config: workerConfig(config),
        });
      },
    }),

    tool({
      name: "kbprep_prepare_batch",
      label: "KBPrep Prepare Batch",
      description:
        "Process a directory of local source files. Runs one sample first and stops the batch if that sample fails quality gates.",
      parameters: Type.Object({
        input_dir: Type.String({ description: "Absolute path to a directory containing local source files." }),
        output_root: Type.String({ description: "Absolute path to kbprep output root." }),
        profile: Type.Optional(
          Type.Union([Type.Literal("lite"), Type.Literal("standard"), Type.Literal("curated_obsidian_kb")], {
            description: "Resource profile. Default 'curated_obsidian_kb'. Use 'standard' only when you explicitly want broad cleaned Markdown.",
          })
        ),
        mode: Type.Optional(
          Type.Union([Type.Literal("rules_only"), Type.Literal("rules_plus_review_pack")], {
            description: "Batch mode. Default 'rules_only'. AI review is single-file only in v1.",
          })
        ),
        force: Type.Optional(Type.Boolean({ description: "Force re-process even if same hash+config. Default false." })),
        artifact_policy: Type.Optional(
          Type.Union([Type.Literal("keep_latest"), Type.Literal("keep_all"), Type.Literal("final_only")], {
            description: "Intermediate artifact retention for each file. Default 'keep_latest'.",
          })
        ),
        language: Type.Optional(Type.String({ description: "Language hint. Default 'zh'." })),
        convert_jobs: Type.Optional(Type.Number({ description: "Max concurrent conversions after the sample passes. Default 1." })),
      }),
      async execute(params, config, ctx) {
        ensureDirectory(params.output_root);
        const pythonPath = await ensurePythonRuntime(config);
        return callWorker("prepare_batch", {
          input_dir: params.input_dir,
          output_root: params.output_root,
          profile: params.profile ?? "curated_obsidian_kb",
          mode: params.mode ?? "rules_only",
          force: params.force ?? false,
          artifact_policy: params.artifact_policy ?? "keep_latest",
          language: params.language ?? "zh",
          convert_jobs: params.convert_jobs ?? 1,
        }, {
          pythonPath,
          cwd: params.output_root,
          timeoutMs: 10_800_000,
          signal: ctx.signal,
          logDir: `${params.output_root}/.kbprep/logs`,
          config: workerConfig(config),
        });
      },
    }),
  ],
});
