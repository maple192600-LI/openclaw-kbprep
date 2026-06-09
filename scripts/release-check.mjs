import { spawnSync } from "node:child_process";

const npm = "npm";
const npx = "npx";

const steps = [
  ["Verify dependency lock dry-run", npm, ["ci", "--dry-run"]],
  ["Reject whitespace errors", "git", ["diff", "--check"]],
  ["Build tracked runtime files without dist drift", "custom", ["build-dist-check"]],
  ["Type-check TypeScript", npx, ["tsc", "-p", "tsconfig.json", "--noEmit"]],
  ["Run TypeScript integration tests", npm, ["test"]],
  ["Lint Python worker", npm, ["run", "python:ruff"]],
  ["Type-check Python worker", npm, ["run", "python:typecheck"]],
  ["Run measured Python coverage", npm, ["run", "python:coverage"]],
  ["Run audit guard checks", npm, ["run", "audit:check"]],
  ["Check npm package contents", npm, ["run", "pack:check"]],
  ["Audit npm dependencies", npm, ["audit", "--audit-level=moderate"]],
];

for (const [label, command, args] of steps) {
  process.stdout.write(`\n==> ${label}\n$ ${[command, ...args].join(" ")}\n`);
  if (command === "custom" && args[0] === "build-dist-check") {
    runBuildDistCheck(label);
    continue;
  }
  const result = runCommand(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    process.stderr.write(`\nrelease:check failed at: ${label}\n`);
    process.exit(result.status ?? 1);
  }
}

process.stdout.write("\nrelease:check passed\n");

function runBuildDistCheck(label) {
  const before = capture("git", ["diff", "--binary", "--", "dist"]);
  runOrFail(npm, ["run", "build"], label);
  const after = capture("git", ["diff", "--binary", "--", "dist"]);
  if (before !== after) {
    process.stderr.write([
      "\nTracked dist output changed after npm run build.",
      "Commit the rebuilt dist files, or inspect why build output is nondeterministic.",
      "Diff after build:",
      after.slice(0, 12000),
      after.length > 12000 ? "\n[diff truncated]\n" : "",
    ].join("\n"));
    process.exit(1);
  }
}

function runOrFail(command, args, label) {
  const result = runCommand(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    process.stderr.write(`\nrelease:check failed at: ${label}\n`);
    process.exit(result.status ?? 1);
  }
}

function capture(command, args) {
  const result = runCommand(command, args, { encoding: "utf8" });
  if (result.status !== 0 && result.status !== 1) {
    process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
    process.exit(result.status ?? 1);
  }
  return result.stdout;
}

function runCommand(command, args, options) {
  if (process.platform === "win32" && (command === "npm" || command === "npx")) {
    return spawnSync("cmd.exe", ["/d", "/s", "/c", command, ...args], {
      ...options,
      shell: false,
    });
  }
  return spawnSync(command, args, {
    ...options,
    shell: false,
  });
}
