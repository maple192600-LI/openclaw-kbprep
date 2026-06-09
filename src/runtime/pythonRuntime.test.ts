import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runtimeSetupStepsForTest, runSetupCommandForTest } from "./pythonRuntime.js";

describe("python runtime setup ergonomics", () => {
  it("exposes bounded setup steps for progress reporting", () => {
    const steps = runtimeSetupStepsForTest();

    expect(steps.map((step) => step.id)).toEqual([
      "create_venv",
      "upgrade_packaging",
      "install_worker",
      "probe_environment",
    ]);
    expect(steps.every((step) => step.timeoutMs > 0)).toBe(true);
    expect(steps.reduce((total, step) => total + step.timeoutMs, 0)).toBeLessThanOrEqual(105 * 60_000);
  });

  it("reports setup command timeout with stderr evidence", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-runtime-timeout-"));
    const scriptPath = path.join(root, "slow-runtime.mjs");
    writeFileSync(scriptPath, [
      "process.stderr.write('before runtime timeout\\n');",
      "setInterval(() => {}, 1000);",
    ].join("\n"), "utf8");

    try {
      await expect(runSetupCommandForTest(
        process.execPath,
        [scriptPath],
        "test runtime timeout",
        100,
      )).rejects.toThrow(/Timed out while trying to test runtime timeout.*before runtime timeout/s);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
