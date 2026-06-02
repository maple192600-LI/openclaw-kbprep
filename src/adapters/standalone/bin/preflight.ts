#!/usr/bin/env node
import { runCli, parseArgs } from "../cli.js";
const { tool, opts } = parseArgs(["kbprep_preflight", ...process.argv.slice(2)]);
process.exit(await runCli(tool, opts));
