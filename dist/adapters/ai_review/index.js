export function resolveBackendName(value) {
    if (value === "local_rules" || value === "claude_code" || value === "codex" || value === "openclaw")
        return value;
    return "openclaw";
}
export function buildBackend(name, options) {
    if (options.explicit)
        return options.explicit;
    if (name === "local_rules")
        return localRulesBackend();
    if (name === "openclaw")
        return openClawSubagentBackend(options.openclawSubagent);
    return missingExternalBackend(name);
}
function localRulesBackend() {
    return {
        async review() {
            return { messages: ["[]"], warning: "W_LLM_REVIEW_LOCAL_RULES: no external AI backend configured; kept deterministic rules-only classifications." };
        },
    };
}
function openClawSubagentBackend(subagent) {
    if (!subagent)
        return undefined;
    return {
        async review(params) {
            const run = await subagent.run({
                sessionKey: params.sessionKey,
                message: params.message,
                provider: params.provider,
                model: params.model,
                extraSystemPrompt: params.systemPrompt,
                lane: "kbprep-review",
                lightContext: true,
                deliver: false,
                idempotencyKey: params.idempotencyKey,
            });
            const waited = await subagent.waitForRun({ runId: run.runId, timeoutMs: params.timeoutMs });
            if (waited.status !== "ok") {
                return {
                    messages: [],
                    warning: `W_LLM_REVIEW_BACKEND_FAILED: ${waited.status}${waited.error ? ` (${waited.error})` : ""}.`,
                };
            }
            const messages = await subagent.getSessionMessages({ sessionKey: params.sessionKey, limit: 20 });
            return { messages: messages.messages };
        },
    };
}
function missingExternalBackend(name) {
    return {
        async review() {
            return {
                messages: [],
                warning: `W_LLM_REVIEW_BACKEND_UNAVAILABLE: ${name} backend is not available in this host runtime.`,
            };
        },
    };
}
