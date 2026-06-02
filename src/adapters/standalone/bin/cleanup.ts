#!/usr/bin/env node
import { runCli, parseArgs } from "../cli.js";
const { tool, opts } = parseArgs(["kbprep_cleanup", ...process.argv.slice(2)]);
process.exit(await runCli(tool, opts));
