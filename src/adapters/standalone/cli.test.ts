import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildCliPlan, parseStandaloneArgs, runStandaloneCli } from "./cli.js";

describe("standalone KBPrep CLI adapter", () => {
  it("prints help without requiring OpenClaw or Python setup", async () => {
    const result = await runStandaloneCli("prepare", ["--help"]);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain("Usage: kbprep-prepare");
    expect(result.output).toContain("--input <file>");
    expect(result.output).toContain("curated_obsidian_kb");
  });

  it("describes cleanup as preserving the profile-specific final deliverable", async () => {
    const result = await runStandaloneCli("cleanup", ["--help"]);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain("Usage: kbprep-cleanup");
    expect(result.output).toContain("profile-specific final deliverable");
    expect(result.output).not.toContain("source-side final outputs");
  });

  it("prints help for every standalone command without touching Python setup", async () => {
    const commands = [
      ["preflight", "kbprep-preflight"],
      ["diagnose", "kbprep-analyze"],
      ["prepare", "kbprep-prepare"],
      ["apply_review", "kbprep-apply-review"],
      ["cleanup", "kbprep-cleanup"],
      ["prepare_batch", "kbprep-batch"],
    ] as const;

    for (const [command, binName] of commands) {
      const result = await runStandaloneCli(command, ["--help"]);
      expect(result.exitCode).toBe(0);
      expect(result.output).toContain(`Usage: ${binName}`);
    }
  });

  it("returns a JSON CLI error when apply-review is missing a patch", async () => {
    const result = await runStandaloneCli("apply_review", ["--run-dir", ".kbprep/missing-patch"]);
    const payload = JSON.parse(result.output) as { ok: boolean; error: { code: string; message: string } };

    expect(result.exitCode).toBe(1);
    expect(payload.ok).toBe(false);
    expect(payload.error.code).toBe("KBPREP_CLI_ERROR");
    expect(payload.error.message).toContain("--patch-file or --patch-json is required");
  });

  it("returns a JSON CLI error for invalid boolean options instead of silently using defaults", async () => {
    const result = await runStandaloneCli("cleanup", [
      "--output",
      ".kbprep/cleanup",
      "--dry-run",
      "maybe",
    ]);
    const payload = JSON.parse(result.output) as { ok: boolean; error: { code: string; message: string } };

    expect(result.exitCode).toBe(1);
    expect(payload.ok).toBe(false);
    expect(payload.error.code).toBe("KBPREP_CLI_ERROR");
    expect(payload.error.message).toContain("--dry-run must be true or false");
  });

  it("maps analyze CLI options to the Python diagnose worker command", () => {
    const parsed = parseStandaloneArgs(["--input", "README.md"]);
    const plan = buildCliPlan("diagnose", parsed.options);

    expect(plan.command).toBe("diagnose");
    expect(plan.input.input_path).toContain("README.md");
    expect(plan.input.output_root).toContain(join(".kbprep", "analyze"));
    expect(plan.input.source_type).toBe("auto");
  });

  it("keeps prepare defaults aligned with the curated knowledge-base profile", () => {
    const parsed = parseStandaloneArgs([
      "--input",
      "README.md",
      "--output",
      ".kbprep/cli-test",
      "--force",
    ]);
    const plan = buildCliPlan("prepare", parsed.options);

    expect(plan.command).toBe("prepare");
    expect(plan.input.profile).toBe("curated_obsidian_kb");
    expect(plan.input.mode).toBe("rules_only");
    expect(plan.input.force).toBe(true);
    expect(plan.input.artifact_policy).toBe("keep_latest");
  });

  it("maps cleanup dry-run options to the Python cleanup worker command", () => {
    const parsed = parseStandaloneArgs([
      "--output",
      ".kbprep/cleanup",
      "--action",
      "expired",
      "--older-than-days",
      "30",
      "--dry-run",
    ]);
    const plan = buildCliPlan("cleanup", parsed.options);

    expect(plan.command).toBe("cleanup");
    expect(plan.input.output_root).toContain(join(".kbprep", "cleanup"));
    expect(plan.input.action).toBe("expired");
    expect(plan.input.older_than_days).toBe(30);
    expect(plan.input.dry_run).toBe(true);
  });

  it("defaults cleanup dry-run to all-artifact preview without weakening finalize cleanup", () => {
    const parsed = parseStandaloneArgs([
      "--output",
      ".kbprep/cleanup",
      "--dry-run",
    ]);
    const plan = buildCliPlan("cleanup", parsed.options);

    expect(plan.command).toBe("cleanup");
    expect(plan.input.action).toBe("all");
    expect(plan.input.dry_run).toBe(true);
  });

  it("maps batch options to the Python prepare_batch worker command", () => {
    const parsed = parseStandaloneArgs([
      "--input",
      "docs",
      "--output",
      ".kbprep/batch",
      "--convert-jobs",
      "2",
      "--force",
    ]);
    const plan = buildCliPlan("prepare_batch", parsed.options);

    expect(plan.command).toBe("prepare_batch");
    expect(plan.input.input_dir).toContain("docs");
    expect(plan.input.output_root).toContain(join(".kbprep", "batch"));
    expect(plan.input.convert_jobs).toBe(2);
    expect(plan.input.force).toBe(true);
    expect(plan.input.profile).toBe("curated_obsidian_kb");
  });

  it("ships standalone bin entries in the npm package manifest", () => {
    const pkg = JSON.parse(readFileSync("package.json", "utf-8")) as {
      bin: Record<string, string>;
      scripts: Record<string, string>;
      peerDependenciesMeta?: Record<string, { optional?: boolean }>;
    };

    expect(pkg.bin["kbprep-preflight"]).toBe("./dist/adapters/standalone/bin/preflight.js");
    expect(pkg.bin["kbprep-analyze"]).toBe("./dist/adapters/standalone/bin/analyze.js");
    expect(pkg.bin["kbprep-prepare"]).toBe("./dist/adapters/standalone/bin/prepare.js");
    expect(pkg.scripts["pack:check"]).toBeDefined();
    expect(pkg.peerDependenciesMeta?.openclaw?.optional).toBe(true);
  });

  it("keeps the standalone adapter independent from the OpenClaw SDK", () => {
    const source = readFileSync("src/adapters/standalone/cli.ts", "utf-8");

    expect(source).not.toContain("openclaw/plugin-sdk");
    expect(source).not.toMatch(/from\s+["']openclaw/);
  });
});
