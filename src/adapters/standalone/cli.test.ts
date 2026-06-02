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

  it("ships standalone bin entries in the npm package manifest", () => {
    const pkg = JSON.parse(readFileSync("package.json", "utf-8")) as {
      bin: Record<string, string>;
      peerDependenciesMeta?: Record<string, { optional?: boolean }>;
    };

    expect(pkg.bin["kbprep-preflight"]).toBe("./dist/adapters/standalone/bin/preflight.js");
    expect(pkg.bin["kbprep-analyze"]).toBe("./dist/adapters/standalone/bin/analyze.js");
    expect(pkg.bin["kbprep-prepare"]).toBe("./dist/adapters/standalone/bin/prepare.js");
    expect(pkg.peerDependenciesMeta?.openclaw?.optional).toBe(true);
  });
});
