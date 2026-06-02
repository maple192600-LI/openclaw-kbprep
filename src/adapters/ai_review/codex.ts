/**
 * OpenAI Codex CLI backend: shells out to `codex` (the standalone Codex
 * CLI, not the VS Code extension) to perform AI review.
 *
 * Prerequisites:
 *   - `codex` CLI installed: `npm i -g @openai/codex`
 *   - `OPENAI_API_KEY` set
 */
import { spawn } from "node:child_process";
import type { AIReviewBackend, AIReviewBatch, AIReviewResponse } from "./backend.js";

export interface CodexBackendOptions {
  /** Absolute path to the `codex` CLI binary. Default: `codex`. */
  cliPath?: string;
  /** Model name (forwarded as `--model`). Default: `gpt-5`. */
  model?: string;
  /** Per-batch timeout in ms. Default: 120_000. */
  timeoutMs?: number;
}

export class CodexBackend implements AIReviewBackend {
  readonly name = "codex" as const;

  constructor(private readonly opts: CodexBackendOptions = {}) {}

  async isAvailable(): Promise<{ available: boolean; reason?: string }> {
    const cli = this.opts.cliPath ?? "codex";
    try {
      await runCapture(cli, ["--version"], 5_000);
      return { available: true };
    } catch (err) {
      return {
        available: false,
        reason: `codex CLI not found or failed (${String(err)}). Install: npm i -g @openai/codex.`,
      };
    }
  }

  async reviewBatch(batch: AIReviewBatch, systemPrompt: string): Promise<AIReviewResponse> {
    const cli = this.opts.cliPath ?? "codex";
    const model = this.opts.model ?? "gpt-5";
    const args = ["exec", "--model", model, "--quiet", `${systemPrompt}\n\n${batch.content}`];

    try {
      const stdout = await runCapture(cli, args, this.opts.timeoutMs ?? 120_000);
      const patches = parseFirstJsonArray(stdout) ?? [];
      return { patches, notes: [`codex backend produced ${patches.length} patch ops`] };
    } catch (err) {
      return { patches: [], notes: [`codex backend error: ${String(err)}`] };
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
