import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import entry, { isRuntimeMarkerCurrent, pluginVenvPythonPath, resolvePythonPath } from "./index.js";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";

type RegisteredTool = {
  name: string;
  execute: (...args: unknown[]) => Promise<unknown>;
};

describe("openclaw-kbprep", () => {
  it("declares tool metadata", () => {
    expect(getToolPluginMetadata(entry)?.tools.map((tool) => tool.name)).toEqual([
      "kbprep_preflight",
      "kbprep_analyze",
      "kbprep_prepare",
      "kbprep_apply_review",
      "kbprep_cleanup",
      "kbprep_prepare_batch",
    ]);
  });

  it("exposes simplified prepare modes", () => {
    const prepare = getToolPluginMetadata(entry)?.tools.find((tool) => tool.name === "kbprep_prepare");

    expect(prepare).toBeDefined();
    expect(JSON.stringify(prepare?.parameters)).toContain("rules_only");
    expect(JSON.stringify(prepare?.parameters)).toContain("rules_plus_review_pack");
    expect(JSON.stringify(prepare?.parameters)).toContain("ai_review");
  });

  it("exposes python_path only as a bootstrap interpreter config", () => {
    const metadata = getToolPluginMetadata(entry);

    expect(JSON.stringify(metadata?.configSchema)).toContain("python_path");
    expect(JSON.stringify(metadata?.configSchema)).toContain("base Python executable");
    expect(JSON.stringify(metadata?.configSchema)).toContain("mineru_timeout_seconds");
  });

  it("targets a plugin-local Python environment instead of a workspace or system dependency environment", () => {
    const runtimePath = pluginVenvPythonPath();

    expect(runtimePath).toContain(join(".kbprep", "venv"));
    expect(runtimePath).toContain(process.platform === "win32" ? join("Scripts", "python.exe") : join("bin", "python"));
    expect(resolvePythonPath(join(tmpdir(), "kbprep-output"))).not.toContain(join(".openclaw", "workspace-wiki"));
  });

  it("rejects stale plugin-local Python runtime markers instead of reusing wrong environments", () => {
    const packageVersion = JSON.parse(readFileSync("package.json", "utf-8")).version;
    const validMarker = {
      schema: "kbprep.plugin_venv.v2",
      plugin_version: packageVersion,
      python_executable: pluginVenvPythonPath(),
      device_override: "auto",
      python_project: {
        dependency_spec: "mineru[all]==3.2.1;PyMuPDF==1.27.2.3;beautifulsoup4==4.14.3;lxml==6.0.2",
      },
      setup_env: { ok: true, data: { device: "cpu" } },
    };

    expect(isRuntimeMarkerCurrent(validMarker)).toBe(true);
    expect(isRuntimeMarkerCurrent({ ...validMarker, schema: "kbprep.plugin_venv.v1" })).toBe(false);
    expect(isRuntimeMarkerCurrent({ ...validMarker, plugin_version: "0.4.0" })).toBe(false);
    expect(isRuntimeMarkerCurrent({ ...validMarker, setup_env: { ok: false } })).toBe(false);
    expect(isRuntimeMarkerCurrent({
      ...validMarker,
      setup_env: { ok: true, data: { actions_taken: ["cuda_install_failed: timed out"] } },
    })).toBe(false);
    expect(isRuntimeMarkerCurrent(validMarker, { device_override: "cpu" })).toBe(false);
  });

  it("runs preflight through the OpenClaw tool registration path", async () => {
    const tempRoot = await mkdtemp(join(tmpdir(), "kbprep-preflight-"));
    const tools = registerTools();
    const preflight = tools.find((tool) => tool.name === "kbprep_preflight");
    expect(preflight).toBeDefined();

    const result = await preflight!.execute(
      "test-call",
      {
        workspace_path: tempRoot,
        profile: "lite",
      },
      undefined,
      undefined,
    );

    const payload = unwrapJsonResult(result);
    const versions = payload.ok ? payload.data.versions : payload.error.details.versions;
    expect(versions.python).toMatch(/^\d+\.\d+\.\d+/);
    expect(versions.python_executable).toContain("python");
    expect(Object.keys(versions)).toContain("mineru_device");
    expect(Object.keys(versions)).toContain("torch_cuda_available");
    expect(Object.keys(versions)).toContain("torch_cuda_version");
    expect(Object.keys(versions)).toContain("torch_device_count");
    expect(Object.keys(versions)).toContain("pymupdf");
    expect(Object.keys(versions)).toContain("pdf_text_layer_available");
  }, 30_000);

  it("describes the plugin as a source-to-markdown cleaner", () => {
    const metadata = getToolPluginMetadata(entry);

    expect(metadata?.description).toContain("clean Markdown");
    expect(metadata?.description).not.toContain("RAG");
  });

  it("runs prepare through the OpenClaw tool registration path", async () => {
    const tempRoot = await mkdtemp(join(tmpdir(), "kbprep-plugin-"));
    const inputPath = join(tempRoot, "raw.md");
    const outputRoot = join(tempRoot, "out");
    await writeFile(
      inputPath,
      [
        "# 实操案例",
        "",
        "第一步，打开工具后台，把模型设置为 gpt-4.1-mini。",
        "",
        "扫码入群领取体验卡。",
      ].join("\n"),
      "utf-8",
    );

    const tools = registerTools({
      runtime: {
        subagent: {
          run: async () => ({ runId: "review-run-1" }),
          waitForRun: async () => ({ status: "ok" }),
          getSessionMessages: async () => ({ messages: [{ content: "[]" }] }),
        },
      },
    });

    const prepare = tools.find((tool) => tool.name === "kbprep_prepare");
    expect(prepare).toBeDefined();

    const result = await prepare!.execute(
      "test-call",
      {
        input_path: inputPath,
        output_root: outputRoot,
        mode: "rules_only",
        force: true,
        language: "zh",
      },
      undefined,
      undefined,
    );

    const payload = unwrapJsonResult(result);
    expect(payload.ok).toBe(true);
    expect(payload.data.latest_outputs.cleaned_md).toContain("cleaned.md");
    expect(payload.data.latest_outputs.diagnosis_report).toContain("diagnosis_report.json");
    expect(payload.data.latest_outputs.obsidian_dir).toContain("obsidian");

    const cleaned = await readFile(payload.data.latest_outputs.cleaned_md, "utf-8");
    const obsidianIndex = await readFile(join(payload.data.latest_outputs.obsidian_dir, "00-索引.md"), "utf-8");
    const discarded = await readFile(payload.data.latest_outputs.discarded_md, "utf-8");
    const diagnosisReport = JSON.parse(await readFile(payload.data.latest_outputs.diagnosis_report, "utf-8"));
    expect(diagnosisReport.schema).toBe("kbprep.diagnosis_report.v1");
    expect(diagnosisReport.detected_format).toBe("markdown");
    expect(diagnosisReport.conversion_strategy).toBe("direct");
    expect(cleaned).toContain("第一步，打开工具后台");
    expect(cleaned).not.toContain("扫码入群领取体验卡");
    expect(obsidianIndex).toContain("[[01-完整正文]]");
    expect(discarded).toContain("扫码入群领取体验卡");
  }, 30_000);

  it("keeps prepare output metadata after AI review publishes the cleaned files", async () => {
    const tempRoot = await mkdtemp(join(tmpdir(), "kbprep-plugin-ai-"));
    const inputPath = join(tempRoot, "raw.md");
    const outputRoot = join(tempRoot, "out");
    await writeFile(
      inputPath,
      [
        "# Tutorial",
        "",
        "1. Open the dashboard and set threshold=0.8.",
        "",
        "Keep the failed case reason and retry_count value.",
      ].join("\n"),
      "utf-8",
    );

    const tools = registerTools({
      runtime: {
        subagent: {
          run: async () => ({ runId: "review-run-1" }),
          waitForRun: async () => ({ status: "ok" }),
          getSessionMessages: async () => ({ messages: [{ content: "[]" }] }),
        },
      },
    });
    const prepare = tools.find((tool) => tool.name === "kbprep_prepare");
    expect(prepare).toBeDefined();

    const result = await prepare!.execute(
      "test-call-ai",
      {
        input_path: inputPath,
        output_root: outputRoot,
        mode: "ai_review",
        force: true,
        language: "zh",
      },
      undefined,
      undefined,
    );

    const payload = unwrapJsonResult(result);
    expect(payload.ok).toBe(true);
    expect(payload.data.run_id).toBeTypeOf("string");
    expect(payload.data.run_dir).toContain("runs");
    expect(payload.data.outputs.cleaned_md).toContain("cleaned.md");
    expect(payload.data.latest_outputs.diagnosis_report).toContain("diagnosis_report.json");
    expect(payload.data.latest_outputs.cleaned_md).toContain("cleaned.md");
    expect(payload.data.ai_review.applied).toBe(0);
    expect(payload.data.ai_review.published).toBe(true);

    const quality = JSON.parse(await readFile(payload.data.latest_outputs.quality_report, "utf-8"));
    expect(quality.runtime.python_executable).toContain("python");
    expect(quality.review_applied_at).toBeTypeOf("number");
  }, 30_000);

  it("validates AI review patches and retries unsafe-only batches", async () => {
    const tempRoot = await mkdtemp(join(tmpdir(), "kbprep-plugin-ai-guard-"));
    const inputPath = join(tempRoot, "raw.md");
    const outputRoot = join(tempRoot, "out");
    await writeFile(
      inputPath,
      [
        "# Tutorial",
        "",
        "1. Open the dashboard and set threshold=0.8.",
        "",
        "This is useful context that should not be rewritten.",
      ].join("\n"),
      "utf-8",
    );

    let runCalls = 0;
    const tools = registerTools({
      runtime: {
        subagent: {
          run: async () => {
            runCalls += 1;
            return { runId: `review-run-${runCalls}` };
          },
          waitForRun: async () => ({ status: "ok" }),
          getSessionMessages: async () => ({
            messages: [
              {
                content: JSON.stringify(runCalls === 1
                  ? [{ op: "replace", path: "/blocks/b_000000/text", value: "summary" }]
                  : [{ op: "replace", path: "/blocks/b_000000/reason", value: "safe classification metadata only" }]),
              },
            ],
          }),
        },
      },
    });
    const prepare = tools.find((tool) => tool.name === "kbprep_prepare");
    expect(prepare).toBeDefined();

    const result = await prepare!.execute(
      "test-call-ai-guard",
      {
        input_path: inputPath,
        output_root: outputRoot,
        mode: "ai_review",
        force: true,
        language: "zh",
      },
      undefined,
      undefined,
    );

    const payload = unwrapJsonResult(result);
    expect(payload.ok).toBe(true);
    expect(runCalls).toBe(2);
    expect(payload.data.ai_review.applied).toBe(1);
    expect(payload.data.ai_review.patch_ops).toBe(1);
    expect(JSON.stringify(payload.warnings ?? [])).toContain("W_LLM_REVIEW_PATCH_OP_REJECTED");

    const cleaned = await readFile(payload.data.latest_outputs.cleaned_md, "utf-8");
    expect(cleaned).toContain("threshold=0.8");
    expect(cleaned).not.toContain("summary");
  }, 30_000);

  it("reviews oversized long-document review packs in batches instead of skipping AI review", async () => {
    const tempRoot = await mkdtemp(join(tmpdir(), "kbprep-plugin-ai-long-"));
    const inputPath = join(tempRoot, "long.md");
    const outputRoot = join(tempRoot, "out");
    const protectedDetail = "Keep tool_name=OpenClaw, threshold=0.8, retry_count=3, failure_reason=timeout, and classification_instruction='classify only'.";
    const repeatedDetail = "This paragraph is ordinary reflective source material about audience pain, positioning, and decision context. It is useful enough to review, but it has no tool names or parameters that should force protection. ";
    const paragraphs = Array.from({ length: 220 }, (_, index) => [
      `## Section ${index + 1}`,
      "",
      `Detail ${index + 1}: ${repeatedDetail.repeat(10)}This is concrete tutorial detail, not summary material.`,
    ].join("\n"));
    await writeFile(inputPath, ["# Long Tutorial", protectedDetail, ...paragraphs].join("\n\n"), "utf-8");

    let runCalls = 0;
    const tools = registerTools({
      runtime: {
        subagent: {
          run: async () => {
            runCalls += 1;
            return { runId: `review-run-${runCalls}` };
          },
          waitForRun: async () => ({ status: "ok" }),
          getSessionMessages: async () => ({ messages: [{ content: "[]" }] }),
        },
      },
    });
    const prepare = tools.find((tool) => tool.name === "kbprep_prepare");
    expect(prepare).toBeDefined();

    const result = await prepare!.execute(
      "test-call-ai-long",
      {
        input_path: inputPath,
        output_root: outputRoot,
        mode: "ai_review",
        force: true,
        language: "zh",
      },
      undefined,
      undefined,
    );

    const payload = unwrapJsonResult(result);
    expect(payload.ok).toBe(true);
    expect(runCalls).toBeGreaterThan(1);
    expect(payload.data.ai_review.batches).toBe(runCalls);
    expect(payload.data.ai_review.published).toBe(true);
    expect(JSON.stringify(payload.warnings ?? [])).not.toContain("review_pack.json is too large");

    const cleaned = await readFile(payload.data.latest_outputs.cleaned_md, "utf-8");
    expect(cleaned).toContain("threshold=0.8");
    expect(cleaned).toContain("retry_count=3");
    expect(cleaned).toContain("classification_instruction='classify only'");
  }, 30_000);
});

function registerTools(apiOverrides: Record<string, unknown> = {}): RegisteredTool[] {
  const tools: RegisteredTool[] = [];
  entry.register({
    pluginConfig: {},
    ...apiOverrides,
    registerTool(tool: RegisteredTool) {
      tools.push(tool);
    },
  } as never);
  return tools;
}

function unwrapJsonResult(result: unknown): any {
  const structured = result as { content?: Array<{ type?: string; text?: string }> };
  const text = structured.content?.find((part) => part.type === "text")?.text;
  if (!text) return result;
  return JSON.parse(text);
}
