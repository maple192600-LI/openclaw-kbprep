/**
 * MCP (Model Context Protocol) server adapter for kbprep.
 *
 * Exposes the Python worker's six core operations as MCP tools so that
 * Codex, Claude Code, Cursor, and any other MCP-compatible agent can call
 * kbprep directly without going through OpenClaw.
 *
 * Transport: stdio (per MCP spec). Run with:
 *
 *     npx -y @modelcontextprotocol/inspector node dist/adapters/mcp/server.js
 *
 * Or install kbprep as a binary and add it to the agent's MCP config:
 *
 *     {
 *       "mcpServers": {
 *         "kbprep": { "command": "kbprep-mcp", "args": [] }
 *       }
 *     }
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { ensurePythonRuntime } from "../python_runtime.js";
import { callWorker, type WorkerConfig } from "../../worker.js";

const TOOL_DEFS = [
  {
    name: "kbprep_preflight",
    description:
      "Read-only runtime readiness check. Reports Python version, MinerU availability, GPU/CPU device, memory, disk, and workspace write permission.",
    inputSchema: {
      type: "object",
      properties: {
        workdir: { type: "string", description: "Working directory for the check." },
        config: {
          type: "object",
          description: "kbprep config override (device_override, max_cpu_threads, etc.).",
        },
      },
    },
  },
  {
    name: "kbprep_analyze",
    description:
      "Read-only diagnosis. Detects file family, PDF subtype, text profile, OCR recommendation.",
    inputSchema: {
      type: "object",
      required: ["input_path"],
      properties: {
        input_path: { type: "string" },
        workdir: { type: "string" },
        config: { type: "object" },
      },
    },
  },
  {
    name: "kbprep_prepare",
    description:
      "Single-file conversion + cleaning pipeline. Produces cleaned.md, discarded.md, quality_report.json beside the source.",
    inputSchema: {
      type: "object",
      required: ["input_path", "output_root"],
      properties: {
        input_path: { type: "string" },
        output_root: { type: "string" },
        mode: {
          type: "string",
          enum: ["rules_only", "rules_plus_review_pack", "ai_review"],
          description: "Default: rules_only.",
        },
        artifact_policy: {
          type: "string",
          enum: ["keep_latest", "keep_all", "final_only"],
        },
        config: { type: "object" },
      },
    },
  },
  {
    name: "kbprep_apply_review",
    description:
      "Apply a JSON Patch 1.0 patch to an existing run's review pack.",
    inputSchema: {
      type: "object",
      required: ["run_dir"],
      properties: {
        run_dir: { type: "string" },
        patch_json: { type: "array" },
      },
    },
  },
  {
    name: "kbprep_cleanup",
    description: "Cleanup intermediate artifacts (finalize / expired / all).",
    inputSchema: {
      type: "object",
      required: ["output_root"],
      properties: {
        output_root: { type: "string" },
        action: { type: "string", enum: ["finalize", "expired", "all"] },
        older_than_days: { type: "number" },
        confirm_review_needed: { type: "boolean" },
      },
    },
  },
  {
    name: "kbprep_prepare_batch",
    description: "Batch conversion of a directory; sample-first stop on fail.",
    inputSchema: {
      type: "object",
      required: ["input_root", "output_root"],
      properties: {
        input_root: { type: "string" },
        output_root: { type: "string" },
        mode: { type: "string", enum: ["rules_only", "rules_plus_review_pack", "ai_review"] },
        sample_first: { type: "boolean", description: "Run one sample and stop on failure." },
        config: { type: "object" },
      },
    },
  },
] as const;

const PYTHON_CONFIG: WorkerConfig = {
  device_override: "auto",
  max_cpu_threads: 4,
  min_free_memory_gb: 4,
  mineru_timeout_seconds: 1140,
};

async function main() {
  const pythonPath = await ensurePythonRuntime();

  const server = new Server(
    { name: "kbprep-mcp", version: "0.5.0" },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOL_DEFS.map((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema,
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request: { params: { name: string; arguments?: Record<string, unknown> } }) => {
    const { name, arguments: args } = request.params;
    const params = (args ?? {}) as Record<string, unknown>;

    let command: string;
    let input: Record<string, unknown>;
    let timeoutMs = 60 * 60_000;

    switch (name) {
      case "kbprep_preflight":
        command = "preflight";
        input = { workdir: params.workdir, config: params.config ?? {} };
        timeoutMs = 30_000;
        break;
      case "kbprep_analyze":
        command = "diagnose";
        input = { input_path: params.input_path, workdir: params.workdir, config: params.config ?? {} };
        timeoutMs = 60_000;
        break;
      case "kbprep_prepare":
        command = "prepare";
        input = {
          input_path: params.input_path,
          output_root: params.output_root,
          mode: params.mode ?? "rules_only",
          artifact_policy: params.artifact_policy ?? "keep_latest",
          config: params.config ?? {},
        };
        timeoutMs = 30 * 60_000;
        break;
      case "kbprep_apply_review":
        command = "apply-review";
        input = { run_dir: params.run_dir, patch_json: params.patch_json ?? [] };
        timeoutMs = 60_000;
        break;
      case "kbprep_cleanup":
        command = "cleanup";
        input = {
          output_root: params.output_root,
          action: params.action ?? "expired",
          older_than_days: params.older_than_days ?? 7,
          confirm_review_needed: params.confirm_review_needed ?? false,
        };
        timeoutMs = 30_000;
        break;
      case "kbprep_prepare_batch":
        command = "prepare-batch";
        input = {
          input_root: params.input_root,
          output_root: params.output_root,
          mode: params.mode ?? "rules_only",
          sample_first: params.sample_first ?? true,
          config: params.config ?? {},
        };
        timeoutMs = 60 * 60_000;
        break;
      default:
        return { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true };
    }

    const result = await callWorker(command, input, {
      pythonPath,
      timeoutMs,
      config: { ...PYTHON_CONFIG, ...((params.config as WorkerConfig) ?? {}) },
    });

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
      isError: !result.ok,
    };
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write("[kbprep-mcp] ready on stdio\n");
}

main().catch((err) => {
  process.stderr.write(`[kbprep-mcp] fatal: ${String(err)}\n`);
  process.exit(1);
});
