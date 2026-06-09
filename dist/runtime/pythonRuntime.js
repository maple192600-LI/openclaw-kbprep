import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ManagedProcessTimeoutError, runManagedProcess } from "./subprocess.js";
const RUNTIME_MARKER_SCHEMA = "kbprep.local_venv.v1";
const PYTHON_WORKER_DEPENDENCY_SPEC = "mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;beautifulsoup4==4.14.3;lxml==6.0.2";
const DEFAULT_RUNTIME_SETUP_STEPS = [
    {
        id: "create_venv",
        label: "create KBPrep local Python virtual environment",
        defaultTimeoutMs: 5 * 60_000,
        env: "KBPREP_CREATE_VENV_TIMEOUT_MS",
    },
    {
        id: "upgrade_packaging",
        label: "upgrade pip in KBPrep local Python virtual environment",
        defaultTimeoutMs: 10 * 60_000,
        env: "KBPREP_UPGRADE_PACKAGING_TIMEOUT_MS",
    },
    {
        id: "install_worker",
        label: "install kbprep worker dependencies into KBPrep local Python virtual environment",
        defaultTimeoutMs: 60 * 60_000,
        env: "KBPREP_INSTALL_WORKER_TIMEOUT_MS",
    },
    {
        id: "probe_environment",
        label: "detect hardware and tune KBPrep local Python dependencies",
        defaultTimeoutMs: 30 * 60_000,
        env: "KBPREP_PROBE_ENVIRONMENT_TIMEOUT_MS",
    },
];
const MIN_RUNTIME_SETUP_TIMEOUT_MS = 30_000;
const MAX_RUNTIME_SETUP_TIMEOUT_MS = 90 * 60_000;
export function resolvePythonPath(_startPath, config) {
    const runtimePython = kbprepVenvPythonPath();
    if (isKbprepVenvReady(config))
        return runtimePython;
    if (shouldSkipAutoSetupForTests()) {
        if (config?.python_path?.trim())
            return config.python_path.trim();
        return process.env.KBPREP_PYTHON
            ?? process.env.PYTHON
            ?? (process.platform === "win32" ? "python" : "python3");
    }
    return runtimePython;
}
export async function ensurePythonRuntime(config, onProgress) {
    const pythonPath = kbprepVenvPythonPath();
    if (isKbprepVenvReady(config))
        return pythonPath;
    if (shouldSkipAutoSetupForTests())
        return resolvePythonPath(kbprepRootDir(), config);
    const venvDir = kbprepVenvDir();
    cleanupStaleKbprepRuntime(config);
    mkdirSync(dirname(venvDir), { recursive: true });
    const bootstrap = bootstrapPythonCommand(config);
    const steps = runtimeSetupSteps();
    await runRuntimeSetupStep(steps[0], onProgress, bootstrap.command, [...bootstrap.args, "-m", "venv", venvDir]);
    await runRuntimeSetupStep(steps[1], onProgress, pythonPath, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]);
    await runRuntimeSetupStep(steps[2], onProgress, pythonPath, ["-m", "pip", "install", "-e", kbprepPythonProjectDir()]);
    const setupResult = await runRuntimeSetupStep(steps[3], onProgress, pythonPath, ["-m", "kbprep_worker.cli", "setup-env", "--json-stdin"], JSON.stringify({ device_override: config?.device_override }));
    const setupEnvelope = parseSetupEnvelope(setupResult.stdout);
    writeFileSync(kbprepVenvReadyMarker(), JSON.stringify({
        schema: RUNTIME_MARKER_SCHEMA,
        created_at: new Date().toISOString(),
        kbprep_version: kbprepPackageVersion(),
        python_executable: pythonPath,
        requested_device_override: config?.device_override ?? null,
        actual_device: actualDeviceFromSetupEnvelope(setupEnvelope),
        python_project: {
            path: kbprepPythonProjectDir(),
            dependency_spec: PYTHON_WORKER_DEPENDENCY_SPEC,
        },
        setup_env: setupEnvelope,
    }, null, 2), "utf-8");
    return pythonPath;
}
function runtimeSetupSteps() {
    return DEFAULT_RUNTIME_SETUP_STEPS.map((step) => ({
        id: step.id,
        label: step.label,
        timeoutMs: runtimeSetupTimeoutMs(step.env, step.defaultTimeoutMs),
    }));
}
export function runtimeSetupStepsForTest() {
    return runtimeSetupSteps();
}
async function runRuntimeSetupStep(step, onProgress, command, args, stdin = "") {
    onProgress?.({ type: "step_start", step });
    const result = await runSetupCommand(command, args, step.label, step.timeoutMs, stdin);
    onProgress?.({ type: "step_success", step });
    return result;
}
function runtimeSetupTimeoutMs(envName, fallback) {
    const raw = process.env[envName];
    if (!raw)
        return fallback;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed <= 0)
        return fallback;
    return Math.min(Math.max(parsed, MIN_RUNTIME_SETUP_TIMEOUT_MS), MAX_RUNTIME_SETUP_TIMEOUT_MS);
}
/*
 * Kept small and exported for characterization tests; production callers should
 * go through ensurePythonRuntime so setup progress is emitted consistently.
 */
export async function runSetupCommandForTest(command, args, label, timeoutMs, stdin = "") {
    return runSetupCommand(command, args, label, timeoutMs, stdin);
}
function kbprepRootDir() {
    const moduleDir = dirname(fileURLToPath(import.meta.url));
    const leaf = basename(moduleDir);
    if (leaf === "dist" || leaf === "src") {
        return resolve(moduleDir, "..");
    }
    if (leaf === "runtime") {
        return resolve(moduleDir, "..", "..");
    }
    return moduleDir;
}
function kbprepPythonProjectDir() {
    return join(kbprepRootDir(), "python");
}
function kbprepVenvDir() {
    return join(kbprepRootDir(), ".kbprep", "venv");
}
function kbprepVenvReadyMarker() {
    return join(kbprepRootDir(), ".kbprep", "runtime-ready.json");
}
function isKbprepVenvReady(config) {
    if (!existsSync(kbprepVenvPythonPath()) || !existsSync(kbprepVenvReadyMarker())) {
        return false;
    }
    return isRuntimeMarkerCurrent(readRuntimeMarker(), config);
}
export function kbprepVenvPythonPath() {
    const venvDir = kbprepVenvDir();
    return process.platform === "win32"
        ? join(venvDir, "Scripts", "python.exe")
        : join(venvDir, "bin", "python");
}
function shouldSkipAutoSetupForTests() {
    return process.env.VITEST === "true" || process.env.KBPREP_SKIP_AUTO_SETUP === "1";
}
function cleanupStaleKbprepRuntime(config) {
    if (!existsSync(kbprepVenvDir()) && !existsSync(kbprepVenvReadyMarker()))
        return;
    if (isKbprepVenvReady(config))
        return;
    assertManagedRuntimePath(kbprepVenvDir());
    rmSync(kbprepVenvDir(), { recursive: true, force: true });
    rmSync(kbprepVenvReadyMarker(), { force: true });
}
function assertManagedRuntimePath(target) {
    const expected = resolve(kbprepRootDir(), ".kbprep", "venv");
    const actual = resolve(target);
    if (actual !== expected) {
        throw new Error(`Refusing to remove unmanaged KBPrep runtime path: ${actual}`);
    }
}
function readRuntimeMarker() {
    try {
        return JSON.parse(readFileSync(kbprepVenvReadyMarker(), "utf-8"));
    }
    catch {
        return null;
    }
}
export function isRuntimeMarkerCurrent(marker, config) {
    if (!marker || typeof marker !== "object")
        return false;
    const data = marker;
    const pythonProject = data.python_project;
    const setupEnv = data.setup_env;
    const setupData = setupEnv?.data;
    return (data.schema === RUNTIME_MARKER_SCHEMA
        && markerVersion(data) === kbprepPackageVersion()
        && data.python_executable === kbprepVenvPythonPath()
        && requestedDeviceOverride(data) === (config?.device_override ?? null)
        && pythonProject?.dependency_spec === PYTHON_WORKER_DEPENDENCY_SPEC
        && setupEnv?.ok === true
        && !hasCudaSetupFailure(setupData));
}
function hasCudaSetupFailure(setupData) {
    const actions = setupData?.actions_taken;
    if (!Array.isArray(actions))
        return false;
    return actions.some((action) => typeof action === "string" && action.startsWith("cuda_install_failed"));
}
function requestedDeviceOverride(marker) {
    if ("requested_device_override" in marker) {
        return marker.requested_device_override === "cuda" || marker.requested_device_override === "cpu"
            ? marker.requested_device_override
            : null;
    }
    return marker.device_override === "cuda" || marker.device_override === "cpu" ? marker.device_override : null;
}
function markerVersion(data) {
    return data.kbprep_version ?? data.plugin_version;
}
function kbprepPackageVersion() {
    try {
        const pkg = JSON.parse(readFileSync(join(kbprepRootDir(), "package.json"), "utf-8"));
        return String(pkg.version || "unknown");
    }
    catch {
        return "unknown";
    }
}
function bootstrapPythonCommand(config) {
    if (config?.python_path?.trim())
        return { command: config.python_path.trim(), args: [] };
    const envBootstrap = process.env.KBPREP_BOOTSTRAP_PYTHON?.trim();
    if (envBootstrap)
        return { command: envBootstrap, args: [] };
    if (process.platform === "win32")
        return { command: "py", args: ["-3"] };
    return { command: "python3", args: [] };
}
async function runSetupCommand(command, args, label, timeoutMs, stdin = "") {
    try {
        const result = await runManagedProcess({
            command,
            args,
            label,
            timeoutMs,
            cwd: kbprepRootDir(),
            stdin,
            env: {
                ...process.env,
                PIP_DISABLE_PIP_VERSION_CHECK: "1",
                PYTHONUTF8: "1",
                PYTHONIOENCODING: "utf-8",
            },
        });
        if (result.code === 0)
            return { stdout: result.stdout, stderr: result.stderr };
        const tail = (result.stderr || result.stdout).split(/\r?\n/).filter(Boolean).slice(-20).join("\n");
        throw new Error(`Failed to ${label} (exit ${result.code}, signal ${result.signal ?? "none"}). ${tail}`);
    }
    catch (err) {
        if (err instanceof ManagedProcessTimeoutError) {
            throw new Error(`Timed out while trying to ${label} after ${err.timeoutMs}ms. ${err.stderrTail || err.stdoutTail}`);
        }
        throw err;
    }
}
function parseSetupEnvelope(stdout) {
    const trimmed = stdout.trim();
    if (!trimmed)
        return null;
    try {
        return JSON.parse(trimmed);
    }
    catch {
        return { raw_stdout_preview: trimmed.slice(0, 500) };
    }
}
function actualDeviceFromSetupEnvelope(envelope) {
    if (!envelope || typeof envelope !== "object")
        return null;
    const data = envelope.data;
    if (!data || typeof data !== "object")
        return null;
    const device = data.device;
    return typeof device === "string" ? device : null;
}
