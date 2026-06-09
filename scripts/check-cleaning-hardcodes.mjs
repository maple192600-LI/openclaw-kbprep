import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const checkedFiles = [
  "python/kbprep_worker/clean_rules.py",
  "python/kbprep_worker/classify_blocks.py",
  "python/kbprep_worker/images.py",
  "python/kbprep_worker/diagnose",
  "python/kbprep_worker/prepare_diagnosis.py",
  "python/kbprep_worker/quality",
  "python/kbprep_worker/obsidian_kb",
  "python/kbprep_worker/feedback",
  "python/kbprep_worker/document_type.py",
];

const baseForbiddenTerms = [
  "PROMOTIONAL_LINE_RE",
  "CONTEXTUAL_CTA_KEYWORDS",
  "SOCIAL_PROFILE_PLATFORMS",
  "BRAND_PROGRAM_PACKAGING_TERMS",
  "公众号",
  "小红书",
  "二维码",
  "扫码",
  "入群",
  "加微信",
  "关注",
];

const fileSpecificForbiddenTerms = {
  "python/kbprep_worker/document_type.py": [
  "课程",
  "报告",
  "摘要",
  "市场规模",
  "订阅",
  "购物车",
  "主持人",
  "嘉宾",
  ],
};

const violations = [];
for (const relative of checkedFiles) {
  const absolute = path.join(repoRoot, relative);
  const forbiddenTerms = [
    ...baseForbiddenTerms,
    ...(fileSpecificForbiddenTerms[relative] ?? []),
  ];
  for (const file of pythonFiles(absolute)) {
    const fileRelative = path.relative(repoRoot, file).replaceAll(path.sep, "/");
    const text = readFileSync(file, "utf8");
    const lines = text.split(/\r?\n/);
    for (const [index, line] of lines.entries()) {
      for (const term of forbiddenTerms) {
        if (line.includes(term)) {
          violations.push({ file: fileRelative, line: index + 1, term });
        }
      }
    }
  }
}

function pythonFiles(target) {
  const stat = statSync(target);
  if (stat.isFile()) {
    return target.endsWith(".py") ? [target] : [];
  }
  return readdirSync(target, { withFileTypes: true })
    .flatMap((entry) => {
      const child = path.join(target, entry.name);
      if (entry.isDirectory()) {
        return pythonFiles(child);
      }
      return entry.isFile() && entry.name.endsWith(".py") ? [child] : [];
    });
}

if (violations.length) {
  process.stderr.write(JSON.stringify({ violations }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({
  checkedFiles: checkedFiles.length,
  baseForbiddenTerms: baseForbiddenTerms.length,
  fileSpecificForbiddenTerms: Object.values(fileSpecificForbiddenTerms).reduce((total, terms) => total + terms.length, 0),
  violations,
}, null, 2));
process.stdout.write("\n");
