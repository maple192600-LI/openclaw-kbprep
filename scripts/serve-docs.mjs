import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const root = resolve("docs");
const requestedPort = Number.parseInt(process.env.PORT || process.argv[2] || "4173", 10);

const contentTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".svg", "image/svg+xml; charset=utf-8"],
  [".webp", "image/webp"],
  [".ico", "image/x-icon"],
]);

function isInsideRoot(filePath) {
  const normalizedRoot = normalize(root + sep);
  return normalize(filePath).startsWith(normalizedRoot);
}

function resolveRequestPath(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0] || "/");
  const cleanPath = decoded === "/" ? "/index.html" : decoded;
  const filePath = resolve(join(root, cleanPath));
  if (!isInsideRoot(filePath)) return null;
  if (!existsSync(filePath) || !statSync(filePath).isFile()) return null;
  return filePath;
}

function makeServer() {
  return createServer((req, res) => {
    const filePath = resolveRequestPath(req.url || "/");
    if (!filePath) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    res.writeHead(200, {
      "content-type": contentTypes.get(extname(filePath).toLowerCase()) || "application/octet-stream",
      "cache-control": "no-store",
    });
    createReadStream(filePath).pipe(res);
  });
}

function listen(port, attemptsLeft = 20) {
  const server = makeServer();
  server.on("error", (error) => {
    if (error.code === "EADDRINUSE" && attemptsLeft > 0) {
      listen(port + 1, attemptsLeft - 1);
      return;
    }
    console.error(error);
    process.exit(1);
  });
  server.listen(port, "127.0.0.1", () => {
    const address = server.address();
    const actualPort = typeof address === "object" && address ? address.port : port;
    console.log(`KB Prep showcase: http://127.0.0.1:${actualPort}/`);
  });
}

listen(Number.isFinite(requestedPort) ? requestedPort : 4173);
