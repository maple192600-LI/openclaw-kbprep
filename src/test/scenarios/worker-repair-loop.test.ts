import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runPython, runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker repair loop", () => {
  it("copies discoverable Markdown assets and publishes only after quality passes", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-repair-assets-"));
    try {
      const sourceDir = path.join(root, "source");
      const outputRoot = path.join(root, "output");
      const assetsDir = path.join(sourceDir, "lesson.assets", "assets");
      mkdirSync(assetsDir, { recursive: true });
      const png1x1 = Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
        "base64",
      );
      writeFileSync(path.join(assetsDir, "step.png"), png1x1);
      const inputPath = path.join(sourceDir, "lesson.md");
      writeFileSync(
        inputPath,
        [
          "# Lesson",
          "",
          "Step 1: keep threshold=0.8.",
          "",
          "![步骤截图](assets/step.png)",
        ].join("\n"),
        "utf8",
      );

      const result = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        source_type: "auto",
        splitter: "auto",
        force: true,
        repair_loop: true,
        max_quality_iterations: 3,
      });

      expect(result.ok).toBe(true);
      expect(existsSync(path.join(outputRoot, "latest.json"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "quality_report.json"))).toBe(true);
      expect(readFileSync(path.join(outputRoot, "cleaned.md"), "utf8")).toContain("threshold=0.8");
      const runDir = result.data.run_dir;
      expect(existsSync(path.join(runDir, "failure_diagnosis.json"))).toBe(true);
      expect(existsSync(path.join(runDir, "repair_plan.md"))).toBe(true);
      expect(existsSync(path.join(runDir, "repair_actions.json"))).toBe(true);
      const diagnosis = JSON.parse(readFileSync(path.join(runDir, "failure_diagnosis.json"), "utf8"));
      expect(diagnosis.failure_types).toContain("missing_assets");
      expect(readFileSync(path.join(runDir, "repair_plan.md"), "utf8")).toContain("assets/step.png");
      expect(JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8")).strict_errors).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("restores discarded detail blocks before publishing final Markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-repair-detail-"));
    try {
      runPython(
        [
          "import json, sys",
          "from pathlib import Path",
          "from kbprep_worker import clean_rules, prepare",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "input_path.write_text('# Lesson\\n\\nStep 1: keep retry_count=3 and threshold=0.8.\\n', encoding='utf-8')",
          "original_apply = clean_rules.apply_clean_rules",
          "def unsafe_apply(blocks, *args, **kwargs):",
          "    blocks = original_apply(blocks, *args, **kwargs)",
          "    for block in blocks:",
          "        if 'retry_count=3' in block.get('text', ''):",
          "            block['status'] = 'discard'",
          "            block['reason'] = 'simulated unsafe cleanup'",
          "    return blocks",
          "clean_rules.apply_clean_rules = unsafe_apply",
          "try:",
          "    prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'standard', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True, 'repair_loop': True, 'max_quality_iterations': 3})",
          "except SystemExit:",
          "    pass",
          "assert (output_root / 'latest.json').exists(), list(output_root.iterdir())",
          "cleaned = (output_root / 'cleaned.md').read_text(encoding='utf-8')",
          "assert 'retry_count=3' in cleaned, cleaned",
          "quality = json.loads((output_root / 'quality_report.json').read_text(encoding='utf-8'))",
          "assert quality['strict_errors'] == [], quality",
          "runs = sorted((output_root / 'runs').iterdir())",
          "assert runs, list(output_root.iterdir())",
          "run_dir = runs[-1]",
          "assert (run_dir / 'failure_diagnosis.json').exists(), list(run_dir.iterdir())",
          "diagnosis = json.loads((run_dir / 'failure_diagnosis.json').read_text(encoding='utf-8'))",
          "assert 'discarded_detail' in diagnosis['failure_types'], diagnosis",
          "assert (run_dir / 'repair_plan.md').exists(), list(run_dir.iterdir())",
          "assert (run_dir / 'repair_actions.json').exists(), list(run_dir.iterdir())",
        ].join("\n"),
        [path.join(root, "lesson.md"), path.join(root, "output")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
