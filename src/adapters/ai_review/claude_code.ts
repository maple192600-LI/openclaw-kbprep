/**
 * Claude Code CLI backend: shells out to `claude` with a one-shot prompt
 * and parses the response. Used by users running kbprep from inside
 * Claude Code (terminal) or from any agent that has the `claude` CLI on PATH.
 *
 * Prerequisites:
 *   - `claude` CLI installed and authenticated
 *   - `claude --print --model <model> "<prompt>"` supported by the installed
 *     version of the CLI
 */
import { spawn } from "node:child_process";
import type { AIReviewBackend, AIReviewBatch, AIReviewResponse } from "./backend.js";

export interface ClaudeCodeBackendOptions {
  /** Absolute path to the `claude` CLI binary. Default: `claude` (resolved from PATH). */
  cliPath?: string;
  /** Model name (forwarded as `--model`). Default: omit (let CLI pick). */
  model?: string;
  /** Per-batch timeout in ms. Default: 120_000. */
  timeoutMs?: number;
}

export class ClaudeCodeBackend implements AIReviewBackend {
  readonly name = "claude_code" as const;

  constructor(private readonly opts: ClaudeCodeBackendOptions = {}) {}

  async isAvailable(): Promise<{ available: boolean; reason?: string }> {
    const cli = this.opts.cliPath ?? "claude";
    try {
      await runCapture(cli, ["--version"], 5_000);
      return { available: true };
    } catch (err) {
      return {
        available: false,
        reason: `claude CLI not found or failed (${String(err)}). Install Claude Code: https://docs.claude.com/en/docs/claude-code.`,
      };
    }
  }

  async reviewBatch(batch: AIReviewBatch, systemPrompt: string): Promise<AIReviewResponse> {
    const cli = this.opts.cliPath ?? "claude";
    const args = ["--print"];
    if (this.opts.model) args.push("--model", this.opts.model);
    args.push("--system", systemPrompt);
    args.push("--append-system-prompt", batch.content);

    try {
      const stdout = await runCapture(cli, args, this.opts.timeoutMs ?? 120_000);
      const patches = parseFirstJsonArray(stdout) ?? [];
      return { patches, notes: [`claude_code backend produced ${patches.length} patch ops`] };
    } catch (err) {
      return { patches: [], notes: [`claude_code backend error: ${String(err)}`] };
    }
  }
}

function runCapture(cmd: string, args: string[], timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`${cmd} timed out after ${timeoutMs}ms`));
    }, timeoutMs);
    child.stdout.on("data", (c: Buffer) => (stdout += c.toString("utf-8")));
    child.stderr.on("data", (c: Buffer) => (stderr += c.toString("utf-8")));
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(stdout);
      else reject(new Error(`${cmd} exited ${code}: ${stderr.trim().slice(0, 500)}`));
    });
  });
}

function parseFirstJsonArray(text: string): Array<Record<string, unknown>> | null {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidates = fenced ? [fenced[1], text] : [text];
  for (const candidate of candidates) {
    const start = candidate.indexOf("[");
    const end = candidate.lastIndexOf("]");
    if (start < 0 || end <= start) continue;
    try {
      const parsed = JSON.parse(candidate.slice(start, end + 1));
      if (Array.isArray(parsed)) return parsed as Array<Record<string, unknown>>;
    } catch {
      /* try next candidate */
    }
  }
  return null;
}
