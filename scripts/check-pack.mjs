import { spawnSync } from "node:child_process";

const requiredFiles = [
  "dist/index.js",
  "dist/adapters/openclaw/index.js",
  "dist/adapters/standalone/cli.js",
  "dist/adapters/standalone/bin/preflight.js",
  "dist/adapters/standalone/bin/analyze.js",
  "dist/adapters/standalone/bin/prepare.js",
  "dist/adapters/standalone/bin/apply-review.js",
  "dist/adapters/standalone/bin/cleanup.js",
  "dist/adapters/standalone/bin/batch.js",
  "dist/runtime/pythonRuntime.js",
  "python/kbprep_worker/obsidian_kb.py",
  "python/kbprep_worker/prepare_diagnosis.py",
  "python/kbprep_worker/prepare_runtime.py",
  "skills/kbprep/SKILL.md",
  "docs/decoupling.md",
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
