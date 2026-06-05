import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const RUNTIME_MARKER_SCHEMA = "kbprep.local_venv.v1";
const PYTHON_WORKER_DEPENDENCY_SPEC = "mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;beautifulsoup4==4.14.3;lxml==6.0.2";
export function resolvePythonPath(_startPath, config) {
    const runtimePython = pluginVenvPythonPath();
    if (isPluginVenvReady(config))
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
export async function ensurePythonRuntime(config) {
    const pythonPath = pluginVenvPythonPath();
    if (isPluginVenvReady(config))
        return pythonPath;
    if (shouldSkipAutoSetupForTests())
        return resolvePythonPath(pluginRootDir(), config);
    const venvDir = pluginVenvDir();
    cleanupStalePluginRuntime(config);
    mkdirSync(dirname(venvDir), { recursive: true });
    const bootstrap = bootstrapPythonCommand(config);
    await runSetupCommand(bootstrap.command, [...bootstrap.args, "-m", "venv", venvDir], "create KBPrep local Python virtual environment", 5 * 60_000);
    await runSetupCommand(pythonPath, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], "upgrade pip in KBPrep local Python virtual environment", 10 * 60_000);
    await runSetupCommand(pythonPath, ["-m", "pip", "install", "-e", pluginPythonProjectDir()], "install kbprep worker dependencies into KBPrep local Python virtual environment", 60 * 60_000);
    const setupResult = await runSetupCommand(pythonPath, ["-m", "kbprep_worker.cli", "setup-env", "--json-stdin"], "detect hardware and tune KBPrep local Python dependencies", 30 * 60_000, JSON.stringify({ device_override: config?.device_override }));
    const setupEnvelope = parseSetupEnvelope(setupResult.stdout);
    writeFileSync(pluginVenvReadyMarker(), JSON.stringify({
        schema: RUNTIME_MARKER_SCHEMA,
        created_at: new Date().toISOString(),
        plugin_version: pluginPackageVersion(),
        python_executable: pythonPath,
        requested_device_override: config?.device_override ?? null,
        actual_device: actualDeviceFromSetupEnvelope(setupEnvelope),
        python_project: {
            path: pluginPythonProjectDir(),
            dependency_spec: PYTHON_WORKER_DEPENDENCY_SPEC,
        },
        setup_env: setupEnvelope,
    }, null, 2), "utf-8");
    return pythonPath;
}
function pluginRootDir() {
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
function pluginPythonProjectDir() {
    return join(pluginRootDir(), "python");
}
function pluginVenvDir() {
    return join(pluginRootDir(), ".kbprep", "venv");
}
function pluginVenvReadyMarker() {
    return join(pluginRootDir(), ".kbprep", "runtime-ready.json");
}
function isPluginVenvReady(config) {
    if (!existsSync(pluginVenvPythonPath()) || !existsSync(pluginVenvReadyMarker())) {
        return false;
    }
    return isRuntimeMarkerCurrent(readRuntimeMarker(), config);
}
export function pluginVenvPythonPath() {
    const venvDir = pluginVenvDir();
    return process.platform === "win32"
        ? join(venvDir, "Scripts", "python.exe")
        : join(venvDir, "bin", "python");
}
export const kbprepVenvPythonPath = pluginVenvPythonPath;
function shouldSkipAutoSetupForTests() {
    return process.env.VITEST === "true" || process.env.KBPREP_SKIP_AUTO_SETUP === "1";
}
function cleanupStalePluginRuntime(config) {
    if (!existsSync(pluginVenvDir()) && !existsSync(pluginVenvReadyMarker()))
        return;
    if (isPluginVenvReady(config))
        return;
    rmSync(pluginVenvDir(), { recursive: true, force: true });
    rmSync(pluginVenvReadyMarker(), { force: true });
}
function readRuntimeMarker() {
    try {
        return JSON.parse(readFileSync(pluginVenvReadyMarker(), "utf-8"));
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
        && data.plugin_version === pluginPackageVersion()
        && data.python_executable === pluginVenvPythonPath()
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
function pluginPackageVersion() {
    try {
        const pkg = JSON.parse(readFileSync(join(pluginRootDir(), "package.json"), "utf-8"));
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
function runSetupCommand(command, args, label, timeoutMs, stdin = "") {
    return new Promise((resolvePromise, reject) => {
        const child = spawn(command, args, {
            cwd: pluginRootDir(),
            stdio: ["pipe", "pipe", "pipe"],
            windowsHide: true,
            env: {
                ...process.env,
                PIP_DISABLE_PIP_VERSION_CHECK: "1",
                PYTHONUTF8: "1",
                PYTHONIOENCODING: "utf-8",
            },
        });
        let stderr = "";
        let stdout = "";
        child.stdout?.on("data", (chunk) => {
            stdout += chunk.toString("utf-8");
        });
        child.stderr?.on("data", (chunk) => {
            stderr += chunk.toString("utf-8");
        });
        if (stdin)
            child.stdin?.end(stdin);
        else
            child.stdin?.end();
        const timer = setTimeout(() => {
            child.kill("SIGTERM");
            reject(new Error(`Timed out while trying to ${label}`));
        }, timeoutMs);
        child.on("close", (code) => {
            clearTimeout(timer);
            if (code === 0) {
                resolvePromise({ stdout, stderr });
                return;
            }
            const tail = (stderr || stdout).split(/\r?\n/).filter(Boolean).slice(-20).join("\n");
            reject(new Error(`Failed to ${label} (exit ${code}). ${tail}`));
        });
        child.on("error", (err) => {
            clearTimeout(timer);
            reject(err);
        });
    });
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
