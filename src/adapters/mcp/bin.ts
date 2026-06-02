#!/usr/bin/env node
import("./server.js").catch((err) => {
  process.stderr.write(`[kbprep-mcp] failed to start: ${String(err)}\n`);
  process.exit(1);
});
