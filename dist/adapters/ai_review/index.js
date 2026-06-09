import { ManagedProcessTimeoutError, runManagedProcess } from "../../runtime/subprocess.js";
export function resolveBackendName(value) {
    if (value === "local_rules" || value === "external")
        return value;
    return "external";
}
export function buildBackend(name, options) {
    if (options.explicit)
        return options.explicit;
    if (name === "local_rules")
        return localRulesBackend();
    if (options.externalCommand?.trim())
        return externalCommandBackend(options.externalCommand.trim());
    return missingExternalBackend(name);
}
function localRulesBackend() {
    return {
        async review() {
            return { messages: ["[]"], warning: "W_LLM_REVIEW_LOCAL_RULES: no external AI backend configured; kept deterministic rules-only classifications." };
        },
    };
}
function missingExternalBackend(name) {
    return {
        async review() {
            return {
                messages: [],
                warning: `W_LLM_REVIEW_BACKEND_UNAVAILABLE: ${name} review backend is not built into standalone KBPrep. Inject a host-provided AIReviewBackend or use rules_plus_review_pack for human/agent review patches.`,
            };
        },
    };
}
function externalCommandBackend(command) {
    return {
        async review(params) {
            const result = await runExternalReviewCommand(command, {
                sessionKey: params.sessionKey,
                message: params.message,
                systemPrompt: params.systemPrompt,
                provider: params.provider,
                model: params.model,
                timeoutMs: params.timeoutMs,
                idempotencyKey: params.idempotencyKey,
            }, params.timeoutMs ?? 60_000);
            return result;
        },
    };
}
function runExternalReviewCommand(command, payload, timeoutMs) {
    return runManagedProcess({
        command,
        label: "AI review command",
        timeoutMs,
        shell: true,
        stdin: JSON.stringify(payload),
    }).then((result) => {
        if (result.code !== 0) {
            rejectExternalCommandExit(result.code, result.stderr);
        }
        try {
            const parsed = JSON.parse(result.stdout.trim());
            if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.messages)) {
                throw new Error("AI review command must return JSON with a messages array.");
            }
            return {
                messages: parsed.messages,
                warning: typeof parsed.warning === "string"
                    ? parsed.warning
                    : undefined,
            };
        }
        catch (err) {
            throw new Error(`AI review command returned invalid JSON: ${String(err)}`);
        }
    }).catch((err) => {
        if (err instanceof ManagedProcessTimeoutError) {
            throw new Error(`AI review command timed out after ${err.timeoutMs}ms. ${err.stderrTail || err.stdoutTail}`);
        }
        throw err;
    });
}
function rejectExternalCommandExit(code, stderr) {
    throw new Error(`AI review command exited ${code}: ${stderr.split(/\r?\n/).filter(Boolean).slice(-10).join("\n")}`);
}
