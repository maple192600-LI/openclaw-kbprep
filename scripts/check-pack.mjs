import { spawnSync } from "node:child_process";

const matrixCheck = spawnSync(process.execPath, ["scripts/check-capability-matrix.mjs"], {
  encoding: "utf-8",
});

if (matrixCheck.status !== 0) {
  process.stderr.write(matrixCheck.stderr || matrixCheck.stdout || String(matrixCheck.error || ""));
  process.exit(matrixCheck.status ?? 1);
}

const hardcodeCheck = spawnSync(process.execPath, ["scripts/check-cleaning-hardcodes.mjs"], {
  encoding: "utf-8",
});

if (hardcodeCheck.status !== 0) {
  process.stderr.write(hardcodeCheck.stderr || hardcodeCheck.stdout || String(hardcodeCheck.error || ""));
  process.exit(hardcodeCheck.status ?? 1);
}

const agentNeutralCheck = spawnSync(process.execPath, ["scripts/check-agent-neutral-runtime.mjs"], {
  encoding: "utf-8",
});

if (agentNeutralCheck.status !== 0) {
  process.stderr.write(agentNeutralCheck.stderr || agentNeutralCheck.stdout || String(agentNeutralCheck.error || ""));
  process.exit(agentNeutralCheck.status ?? 1);
}

const auditCheck = spawnSync(process.execPath, ["scripts/check-audit-remediation.mjs"], {
  encoding: "utf-8",
});

if (auditCheck.status !== 0) {
  process.stderr.write(auditCheck.stderr || auditCheck.stdout || String(auditCheck.error || ""));
  process.exit(auditCheck.status ?? 1);
}

const thresholdCheck = spawnSync(process.execPath, ["scripts/check-thresholds.mjs"], {
  encoding: "utf-8",
});

if (thresholdCheck.status !== 0) {
  process.stderr.write(thresholdCheck.stderr || thresholdCheck.stdout || String(thresholdCheck.error || ""));
  process.exit(thresholdCheck.status ?? 1);
}

const requiredFiles = [
  "dist/index.js",
  "dist/adapters/standalone/cli.js",
  "dist/adapters/standalone/bin/preflight.js",
  "dist/adapters/standalone/bin/analyze.js",
  "dist/adapters/standalone/bin/prepare.js",
  "dist/adapters/standalone/bin/apply-review.js",
  "dist/adapters/standalone/bin/feedback.js",
  "dist/adapters/standalone/bin/cleanup.js",
  "dist/adapters/standalone/bin/batch.js",
  "dist/runtime/pythonRuntime.js",
  "python/kbprep_worker/obsidian_kb/__init__.py",
  "python/kbprep_worker/obsidian_kb/body_notes.py",
  "python/kbprep_worker/obsidian_kb/context.py",
  "python/kbprep_worker/obsidian_kb/frontmatter.py",
  "python/kbprep_worker/obsidian_kb/links.py",
  "python/kbprep_worker/obsidian_kb/policy.py",
  "python/kbprep_worker/obsidian_kb/signals.py",
  "python/kbprep_worker/obsidian_kb/titles.py",
  "python/kbprep_worker/diagnose/__init__.py",
  "python/kbprep_worker/obsidian_template.py",
  "python/kbprep_worker/converter_capabilities.py",
  "python/kbprep_worker/document_type_signals.py",
  "python/kbprep_worker/prepare_diagnosis.py",
  "python/kbprep_worker/prepare_runtime.py",
  "python/kbprep_worker/repair_loop.py",
  "python/kbprep_worker/quality/__init__.py",
  "python/kbprep_worker/quality/runner.py",
  "python/kbprep_worker/quality/gates.py",
  "python/kbprep_worker/quality/retention.py",
  "python/kbprep_worker/feedback/__init__.py",
  "python/kbprep_worker/feedback/command.py",
  "python/kbprep_worker/feedback/proposals.py",
  "python/kbprep_worker/feedback/rerun_verification.py",
  "python/kbprep_worker/title_filters.py",
  "rules/base/obvious_noise.json",
  "rules/base/document_type_signals.json",
  "rules/base/ocr_normalization.json",
  "rules/base/title_filters.json",
  "rules/templates/obsidian_generic.json",
  "rules/templates/obsidian_course_kb.json",
  "rules/templates/self_media_course.json",
  "rules/user/proposed_rules.jsonl",
  "rules/user/accepted_rules.jsonl",
  "rules/user/rejected_rules.jsonl",
  "skills/kbprep/SKILL.md",
  "AGENTS.md",
  "docs/agent-neutral.md",
  "docs/audit-remediation.md",
  "docs/capability-matrix.md",
  "docs/quality-loop.md",
  "docs/feedback-learning.md",
  "docs/hardcoded-cleaning-inventory.md",
  "docs/install/claude-code.md",
  "docs/install/codex.md",
  "docs/install/openclaw.md",
  "docs/install/hermes.md",
  "docs/known-issues.md",
  "docs/risk-tags.md",
  "docs/standalone-cli.md",
  "CHANGELOG.md",
  "LICENSE",
];

const npmCommand = process.platform === "win32" ? "cmd.exe" : "npm";
const npmArgs = process.platform === "win32"
  ? ["/d", "/s", "/c", "npm", "pack", "--dry-run", "--json"]
  : ["pack", "--dry-run", "--json"];
const result = spawnSync(npmCommand, npmArgs, {
  encoding: "utf-8",
});

if (result.status !== 0) {
  process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
  process.exit(result.status ?? 1);
}

let pack;
try {
  pack = JSON.parse(result.stdout)[0];
} catch (error) {
  process.stderr.write(`Failed to parse npm pack JSON: ${error}\n${result.stdout}`);
  process.exit(1);
}

const files = new Set(pack.files.map((file) => file.path));
const missing = requiredFiles.filter((file) => !files.has(file));

if (missing.length > 0) {
  process.stderr.write(`npm package is missing required files:\n${missing.map((file) => `- ${file}`).join("\n")}\n`);
  process.exit(1);
}

process.stdout.write(JSON.stringify({
  filename: pack.filename,
  version: pack.version,
  fileCount: pack.files.length,
  checked: requiredFiles.length,
}, null, 2));
process.stdout.write("\n");
