import { describe, expect, it } from "vitest";
import { parseEnvelope } from "./worker.js";

describe("worker command data schemas", () => {
  it("rejects prepare envelopes missing run_dir", () => {
    const envelope = JSON.stringify({
      ok: true,
      data: {
        run_id: "run-1",
        latest_outputs: {},
      },
    });

    const result = parseEnvelope(envelope, [], "prepare");

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
    expect(result.error?.details.validation_errors).toBeDefined();
    expect(result.error?.details.command).toBe("prepare");
  });

  it("accepts prepare envelopes with required output contract", () => {
    const envelope = JSON.stringify({
      ok: true,
      data: {
        run_id: "run-1",
        run_dir: "C:/tmp/run-1",
        latest_outputs: {},
      },
      warnings: [],
    });

    const result = parseEnvelope(envelope, [], "prepare");

    expect(result.ok).toBe(true);
    expect(result.data?.run_dir).toBe("C:/tmp/run-1");
  });

  it("rejects cleanup envelopes with non-object data", () => {
    const envelope = JSON.stringify({
      ok: true,
      data: "cleaned",
    });

    const result = parseEnvelope(envelope, [], "cleanup");

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
  });
});
