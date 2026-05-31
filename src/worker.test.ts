import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function pythonCommand(usePluginRuntime = false) {
  const override = process.env.KBPREP_TEST_PYTHON;
  if (override) return { command: override, prefix: [] as string[] };
  const venvPython = process.platform === "win32"
    ? path.join(repoRoot, ".kbprep", "venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".kbprep", "venv", "bin", "python");
  if (usePluginRuntime && existsSync(venvPython)) return { command: venvPython, prefix: [] as string[] };
  return process.platform === "win32"
    ? { command: "py", prefix: ["-3"] }
    : { command: "python3", prefix: [] as string[] };
}

function shouldUsePluginRuntime(payload: Record<string, unknown>) {
  const inputPath = typeof payload.input_path === "string" ? payload.input_path : "";
  const ext = path.extname(inputPath).toLowerCase();
  return new Set([
    ".pdf", ".mobi", ".doc", ".ppt", ".xls",
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif",
  ]).has(ext);
}

function runWorker(command: string, payload: Record<string, unknown>, expectedStatus = 0) {
  const python = pythonCommand(shouldUsePluginRuntime(payload));
  const result = spawnSync(python.command, [...python.prefix, "-m", "kbprep_worker.cli", command, "--json-stdin"], {
    cwd: repoRoot,
    input: JSON.stringify(payload),
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONPATH: path.join(repoRoot, "python"),
      PYTHONUTF8: "1",
    },
    timeout: 30_000,
  });

  expect(result.status, result.stderr).toBe(expectedStatus);
  const lines = result.stdout.trim().split(/\r?\n/).filter(Boolean);
  return JSON.parse(lines.at(-1) ?? "{}");
}

function runWorkerRawInput(command: string, rawInput: string, expectedStatus = 0) {
  const python = pythonCommand();
  const result = spawnSync(python.command, [...python.prefix, "-m", "kbprep_worker.cli", command, "--json-stdin"], {
    cwd: repoRoot,
    input: rawInput,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONPATH: path.join(repoRoot, "python"),
      PYTHONUTF8: "1",
    },
    timeout: 30_000,
  });

  expect(result.status, result.stderr).toBe(expectedStatus);
  const lines = result.stdout.trim().split(/\r?\n/).filter(Boolean);
  return JSON.parse(lines.at(-1) ?? "{}");
}

function runPython(code: string, args: string[], usePluginRuntime = false) {
  const python = pythonCommand(usePluginRuntime);
  const result = spawnSync(python.command, [...python.prefix, "-", ...args], {
    cwd: repoRoot,
    input: code,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONPATH: path.join(repoRoot, "python"),
      PYTHONUTF8: "1",
    },
    timeout: 30_000,
  });

  expect(result.status, result.stderr).toBe(0);
}

function makeTextLayerPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "page.insert_text((72, 72), 'Step 1: open settings and set threshold to 0.8.')",
      "page.insert_text((72, 96), 'Step 2: record failure details and retry_count values.')",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

function makeImageOnlyPdf(pdfPath: string, imagePath: string) {
  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64",
  );
  writeFileSync(imagePath, png1x1);
  runPython(
    [
      "import fitz, sys",
      "pdf_path, image_path = sys.argv[1], sys.argv[2]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "page.insert_image(fitz.Rect(72, 72, 320, 320), filename=image_path)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath, imagePath],
    true,
  );
}

function makeLandscapeImagePdf(pdfPath: string, imagePath: string) {
  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64",
  );
  writeFileSync(imagePath, png1x1);
  runPython(
    [
      "import fitz, sys",
      "pdf_path, image_path = sys.argv[1], sys.argv[2]",
      "doc = fitz.open()",
      "for _ in range(3):",
      "    page = doc.new_page(width=1280, height=720)",
      "    page.insert_image(fitz.Rect(0, 0, 1280, 720), filename=image_path)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath, imagePath],
    true,
  );
}

function makeLandscapeTextPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "for index in range(4):",
      "    page = doc.new_page(width=1280, height=720)",
      "    page.insert_text((72, 72), f'Slide {index + 1}: keep concrete setup step threshold=0.8.')",
      "    page.insert_text((72, 104), 'Record retry_count=3 and failure_reason=timeout.')",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

function makeGarbledTextLayerPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "garbled = 'Ჭ䌦圳➉ᵜⰭ䕇✮⦽ ' * 80",
      "for index in range(6):",
      "    page = doc.new_page(width=595, height=842)",
      "    page.insert_textbox(fitz.Rect(72, 72, 520, 760), garbled)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

function makeOfficeFixtures(docxPath: string, pptxPath: string, xlsxPath: string) {
  runPython(
    [
      "import base64, sys, zipfile",
      "docx_path, pptx_path, xlsx_path = sys.argv[1:4]",
      "png1x1 = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=')",
      "def write_zip(path, files):",
      "    with zipfile.ZipFile(path, 'w') as z:",
      "        for name, content in files.items():",
      "            z.writestr(name, content)",
      "write_zip(docx_path, {",
      "  '[Content_Types].xml': '<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>',",
      "  'word/document.xml': '''<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>",
      "    <w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>DOCX Tutorial</w:t></w:r></w:p>",
      "    <w:p><w:r><w:t>Open the dashboard and set threshold=0.8 before exporting.</w:t></w:r></w:p>",
      "    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Field</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr>",
      "    <w:tr><w:tc><w:p><w:r><w:t>retry_count</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>3</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
      "  </w:body></w:document>'''",
      "})",
      "write_zip(pptx_path, {",
      "  '[Content_Types].xml': '<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>',",
      "  'ppt/slides/slide1.xml': '''<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><p:cSld><p:spTree>",
      "    <p:sp><p:txBody><a:p><a:r><a:t>PPT Tutorial Slide</a:t></a:r></a:p><a:p><a:r><a:t>Keep platform setup steps and failure_reason=timeout.</a:t></a:r></a:p></p:txBody></p:sp>",
      "    <p:pic><p:blipFill><a:blip r:embed=\"rIdImage1\"/></p:blipFill></p:pic>",
      "  </p:spTree></p:cSld></p:sld>''',",
      "  'ppt/slides/_rels/slide1.xml.rels': '''<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rIdImage1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" Target=\"../media/step.png\"/></Relationships>''',",
      "  'ppt/media/step.png': png1x1,",
      "  'ppt/slides/slide2.xml': '''<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><p:cSld><p:spTree>",
      "    <p:sp><p:txBody><a:p><a:r><a:t>PPT Case Slide</a:t></a:r></a:p><a:p><a:r><a:t>Record retry_count=3 and keep the failed account example.</a:t></a:r></a:p></p:txBody></p:sp>",
      "  </p:spTree></p:cSld></p:sld>'''",
      "})",
      "write_zip(xlsx_path, {",
      "  '[Content_Types].xml': '<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>',",
      "  'xl/workbook.xml': '''<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheets><sheet name=\"Params\" sheetId=\"1\" r:id=\"rId1\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"/></sheets></workbook>''',",
      "  'xl/sharedStrings.xml': '''<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><si><t>Name</t></si><si><t>Value</t></si><si><t>threshold</t></si><si><t>0.8</t></si></sst>''',",
      "  'xl/worksheets/sheet1.xml': '''<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData><row><c t=\"s\"><v>0</v></c><c t=\"s\"><v>1</v></c></row><row><c t=\"s\"><v>2</v></c><c t=\"s\"><v>3</v></c></row></sheetData></worksheet>'''",
      "})",
    ].join("\n"),
    [docxPath, pptxPath, xlsxPath],
  );
}

function makeEpubFixture(epubPath: string) {
  runPython(
    [
      "import sys, zipfile",
      "epub_path = sys.argv[1]",
      "files = {",
      "  'mimetype': 'application/epub+zip',",
      "  'META-INF/container.xml': '''<?xml version=\"1.0\"?><container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\"><rootfiles><rootfile full-path=\"OEBPS/content.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles></container>''',",
      "  'OEBPS/content.opf': '''<?xml version=\"1.0\"?><package version=\"3.0\" xmlns=\"http://www.idpf.org/2007/opf\"><manifest><item id=\"c1\" href=\"chapter1.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"c2\" href=\"chapter2.xhtml\" media-type=\"application/xhtml+xml\"/></manifest><spine><itemref idref=\"c1\"/><itemref idref=\"c2\"/></spine></package>''',",
      "  'OEBPS/chapter1.xhtml': '''<html xmlns=\"http://www.w3.org/1999/xhtml\"><body><h1>第一章 工具准备</h1><p>第一步：打开 OpenClaw 后台，把 threshold=0.8，并记录 failure_reason=timeout。</p><p>这一步必须保留工具名、参数和失败原因。</p></body></html>''',",
      "  'OEBPS/chapter2.xhtml': '''<html xmlns=\"http://www.w3.org/1999/xhtml\"><body><h1>第二章 案例复盘</h1><p>案例：账号设置里出现 retry_count=3 时，需要记录限制条件，不能总结成一句话。</p><p>扫码加入社群领取体验卡。</p></body></html>''',",
      "}",
      "with zipfile.ZipFile(epub_path, 'w') as z:",
      "    for name, content in files.items():",
      "        z.writestr(name, content)",
    ].join("\n"),
    [epubPath],
  );
}

function normalizeMarkdownText(text: string) {
  return text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
}

describe("kbprep worker pipeline", () => {
  it("maps common Chinese language hints to MinerU language codes", () => {
    runPython(
      [
        "from kbprep_worker.mineru_adapter import normalize_mineru_language",
        "assert normalize_mineru_language('zh') == 'ch'",
        "assert normalize_mineru_language('zh-CN') == 'ch'",
        "assert normalize_mineru_language('zh_tw') == 'chinese_cht'",
        "assert normalize_mineru_language(None) == 'ch'",
        "assert normalize_mineru_language('en') == 'en'",
      ].join("\n"),
      [],
    );
  });

  it("discovers MinerU 3.2 auto output files under the stem directory", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-mineru-discovery-"));
    try {
      runPython(
        [
          "import subprocess, sys",
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter",
          "root = Path(sys.argv[1])",
          "input_path = root / 'sample.pdf'",
          "input_path.write_bytes(b'%PDF-1.4\\n')",
          "class Proc:",
          "    returncode = 0",
          "    stdout = ''",
          "    stderr = ''",
          "def fake_run(cmd, **kwargs):",
          "    out = Path(cmd[cmd.index('-o') + 1])",
          "    auto = out / input_path.stem / 'auto'",
          "    auto.mkdir(parents=True)",
          "    (auto / f'{input_path.stem}.md').write_text('# OCR\\n', encoding='utf-8')",
          "    (auto / f'{input_path.stem}_content_list.json').write_text('[]', encoding='utf-8')",
          "    (auto / f'{input_path.stem}_content_list_v2.json').write_text('[]', encoding='utf-8')",
          "    (auto / f'{input_path.stem}_middle.json').write_text('{}', encoding='utf-8')",
          "    return Proc()",
          "mineru_adapter.find_mineru = lambda: 'mineru'",
          "subprocess.run = fake_run",
          "result = mineru_adapter.run_mineru(str(input_path), str(root / 'run'), language='zh', mode='auto')",
          "assert result['source_md_path'].endswith('source.md'), result",
          "assert result['content_list_path'].endswith('_content_list.json'), result",
          "assert result['content_list_v2_path'].endswith('_content_list_v2.json'), result",
          "assert result['middle_json_path'].endswith('_middle.json'), result",
          "assert result['warnings'] == [], result",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not count common Markdown punctuation as garbled PDF text", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "text = '第一步：打开 A—B 设置页，填写 threshold=0.8，并记录 [retry_count]。'",
        "quality = analyze_text_quality(text)",
        "assert quality['non_common_unicode_ratio'] == 0.0, quality",
        "assert quality['garbled_ratio'] == 0.0, quality",
      ].join("\n"),
      [],
    );
  });

  it("detects readable QR and CTA pollution text during diagnosis", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "quality = analyze_text_quality('扫码进群，长按识别二维码，添加老师免费领取体验卡。')",
        "assert quality['has_qr_text'] is True, quality",
        "assert quality['has_cta_text'] is True, quality",
      ].join("\n"),
      [],
    );
  });

  it("detects Chinese mojibake from broken PDF text layers", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "text = '鐩綍\\nOpenClaw 鏄粈涔?\\n閮ㄧ讲鏂规\\nSkills 绯荤粺'",
        "quality = analyze_text_quality(text * 20)",
        "normal = analyze_text_quality('今天讲一下教程步骤、参数和失败经验。' * 20)",
        "assert normal['mojibake_ratio'] == 0.0, normal",
        "assert quality['mojibake_ratio'] > 0.08, quality",
        "assert quality['unreadable_text_ratio'] > 0.08, quality",
      ].join("\n"),
      [],
    );
  });

  it("detects common UTF-8-as-GBK PDF text-layer mojibake", () => {
    runPython(
      [
        "from kbprep_worker.diagnose import analyze_text_quality",
        "broken_pdf_text = 'OpenClaw姗欑毊涔︿粠鍏ラ棬鍒扮簿閫氾紝娑电洊鏋舵瀯鍘熺悊銆侀儴缃叉柟妗堛€佹笭閬撴帴鍏ャ€丼kills绯荤粺'",
        "quality = analyze_text_quality(broken_pdf_text * 10)",
        "normal = analyze_text_quality('今天讲一个教程步骤、参数和失败经验。OpenClaw 可以接入多种渠道。' * 20)",
        "assert normal['mojibake_ratio'] == 0.0, normal",
        "assert quality['mojibake_ratio'] > 0.08, quality",
        "assert quality['unreadable_text_ratio'] > 0.08, quality",
      ].join("\n"),
      [],
    );
  });

  it("installs pinned CUDA torch into the selected plugin Python and re-probes in a fresh process", () => {
    runPython(
      [
        "import json",
        "from kbprep_worker import setup_env",
        "calls = []",
        "state = {'cuda_installed': False}",
        "class Proc:",
        "    def __init__(self, returncode=0, stdout='', stderr=''):",
        "        self.returncode = returncode",
        "        self.stdout = stdout",
        "        self.stderr = stderr",
        "def fake_which(name):",
        "    return 'C:/Windows/System32/nvidia-smi.exe' if name == 'nvidia-smi' else None",
        "def fake_run(cmd, **kwargs):",
        "    calls.append(cmd)",
        "    if cmd[:3] == ['venv-python', '-m', 'pip']:",
        "        state['cuda_installed'] = True",
        "        return Proc()",
        "    if cmd[:2] == ['venv-python', '-c']:",
        "        payload = {'installed': True, 'version': '2.8.0+cpu', 'cuda_available': False, 'cuda_version': 'none', 'device_count': 0, 'device': 'cpu'}",
        "        if state['cuda_installed']:",
        "            payload = {'installed': True, 'version': '2.8.0+cu126', 'cuda_available': True, 'cuda_version': '12.6', 'device_count': 1, 'device': 'cuda', 'device_name': 'RTX Test', 'vram_gb': 16.0}",
        "        return Proc(stdout=json.dumps(payload))",
        "    raise AssertionError(cmd)",
        "setup_env.shutil.which = fake_which",
        "setup_env.subprocess.run = fake_run",
        "result = setup_env.setup_gpu('venv-python')",
        "pip_calls = [cmd for cmd in calls if cmd[:3] == ['venv-python', '-m', 'pip']]",
        "assert len(pip_calls) == 1, calls",
        "assert 'torch==2.8.0' in pip_calls[0], pip_calls",
        "assert 'torchvision==0.23.0' in pip_calls[0], pip_calls",
        "assert '--force-reinstall' in pip_calls[0], pip_calls",
        "assert 'https://download.pytorch.org/whl/cu126' in pip_calls[0], pip_calls",
        "assert calls[-2][2] == setup_env._torch_probe_code(), calls",
        "assert result['torch_cuda'] is True, result",
        "assert result['device'] == 'cuda', result",
        "assert result['gpu']['device_name'] == 'RTX Test', result",
      ].join("\n"),
      [],
    );
  });

  it("does not install CUDA torch when plugin config forces CPU mode", () => {
    runPython(
      [
        "import json",
        "from kbprep_worker import setup_env",
        "calls = []",
        "class Proc:",
        "    def __init__(self, returncode=0, stdout='', stderr=''):",
        "        self.returncode = returncode",
        "        self.stdout = stdout",
        "        self.stderr = stderr",
        "def fake_which(name):",
        "    return 'C:/Windows/System32/nvidia-smi.exe' if name == 'nvidia-smi' else None",
        "def fake_run(cmd, **kwargs):",
        "    calls.append(cmd)",
        "    if cmd[:2] == ['venv-python', '-c']:",
        "        payload = {'installed': True, 'version': '2.8.0+cpu', 'cuda_available': False, 'cuda_version': 'none', 'device_count': 0, 'device': 'cpu'}",
        "        return Proc(stdout=json.dumps(payload))",
        "    raise AssertionError(cmd)",
        "setup_env.shutil.which = fake_which",
        "setup_env.subprocess.run = fake_run",
        "result = setup_env.setup_gpu('venv-python', device_override='cpu')",
        "assert not [cmd for cmd in calls if cmd[:3] == ['venv-python', '-m', 'pip']], calls",
        "assert result['actions_taken'] == ['cuda_install_skipped_device_override_cpu'], result",
        "assert result['device_override'] == 'cpu', result",
      ].join("\n"),
      [],
    );
  });

  it("prefers MinerU installed beside the selected Python executable", () => {
    runPython(
      [
        "from pathlib import Path",
        "import sys, tempfile",
        "from kbprep_worker.mineru_adapter import find_mineru",
        "root = Path(tempfile.mkdtemp())",
        "scripts = root / 'Scripts'",
        "scripts.mkdir()",
        "(scripts / 'python.exe').write_text('', encoding='utf-8')",
        "(scripts / 'mineru.exe').write_text('', encoding='utf-8')",
        "old = sys.executable",
        "try:",
        "    sys.executable = str(scripts / 'python.exe')",
        "    assert find_mineru() == str(scripts / 'mineru.exe')",
        "finally:",
        "    sys.executable = old",
      ].join("\n"),
      [],
    );
  });

  it("does not fall back to a system MinerU outside the selected Python environment", () => {
    runPython(
      [
        "from pathlib import Path",
        "import os, sys, tempfile",
        "from kbprep_worker.mineru_adapter import find_mineru",
        "root = Path(tempfile.mkdtemp())",
        "scripts = root / 'Scripts'",
        "external = root / 'external'",
        "scripts.mkdir()",
        "external.mkdir()",
        "(scripts / 'python.exe').write_text('', encoding='utf-8')",
        "(external / 'mineru.exe').write_text('', encoding='utf-8')",
        "old_executable = sys.executable",
        "old_path = os.environ.get('PATH', '')",
        "try:",
        "    sys.executable = str(scripts / 'python.exe')",
        "    os.environ['PATH'] = str(external)",
        "    try:",
        "        find_mineru()",
        "    except FileNotFoundError as exc:",
        "        assert str(scripts) in str(exc)",
        "    else:",
        "        raise AssertionError('find_mineru unexpectedly used PATH outside selected venv')",
        "finally:",
        "    sys.executable = old_executable",
        "    os.environ['PATH'] = old_path",
      ].join("\n"),
      [],
    );
  });

  it("maps MinerU content_list pages to block and chunk page ranges by line position", () => {
    runPython(
      [
        "import json, tempfile",
        "from pathlib import Path",
        "from kbprep_worker.blockify import blockify",
        "from kbprep_worker.split import split_into_chunks",
        "run_dir = Path(tempfile.mkdtemp(prefix='kbprep-page-map-'))",
        "content_list = run_dir / 'content_list.json'",
        "text = '\\n'.join([",
        "  '# Page One',",
        "  '',",
        "  'First page keeps setup detail and threshold=0.7.',",
        "  '',",
        "  '# Page Two',",
        "  '',",
        "  'Second page keeps retry_count=3 and failure_reason=timeout.',",
        "])",
        "content_list.write_text(json.dumps([",
        "  {'page_idx': 0, 'text': '# Page One\\n\\nFirst page keeps setup detail'},",
        "  {'page_idx': 1, 'text': '# Page Two\\n\\nSecond page keeps retry_count'},",
        "]), encoding='utf-8')",
        "blocks = blockify(text, 'abcdef1234567890', {'content_list_path': str(content_list)}, str(run_dir))",
        "first = next(b for b in blocks if 'First page' in b['text'])",
        "second = next(b for b in blocks if 'Second page' in b['text'])",
        "assert first['page_start'] == 0 and first['page_end'] == 0, first",
        "assert second['page_start'] == 1 and second['page_end'] == 1, second",
        "for block in blocks: block['status'] = 'keep'",
        "split_into_chunks(blocks, str(run_dir), 'pdf_like', 'abcdef1234567890', 'run123')",
        "chunk_text = (run_dir / 'chunks' / 'chunk_0001.md').read_text(encoding='utf-8')",
        "assert 'page_range: \"0-1\"' in chunk_text, chunk_text.split('\\n')[:8]",
      ].join("\n"),
      [],
    );
  });

  it("uses slide/page order split strategy only when diagnosis requests it", () => {
    runPython(
      [
        "import json, tempfile",
        "from pathlib import Path",
        "from kbprep_worker.split import split_into_chunks",
        "def blocks():",
        "    return [",
        "      {'block_id': 'p1h', 'status': 'keep', 'type': 'section_heading', 'text': '# Slide 1', 'heading_path': ['Slide 1'], 'page_start': 0, 'page_end': 0},",
        "      {'block_id': 'p1b', 'status': 'keep', 'type': 'paragraph', 'text': 'Slide 1 keeps threshold=0.8 and setup details.', 'heading_path': ['Slide 1'], 'page_start': 0, 'page_end': 0},",
        "      {'block_id': 'p2h', 'status': 'keep', 'type': 'section_heading', 'text': '# Slide 2', 'heading_path': ['Slide 2'], 'page_start': 1, 'page_end': 1},",
        "      {'block_id': 'p2b', 'status': 'keep', 'type': 'paragraph', 'text': 'Slide 2 keeps retry_count=3 and failure_reason=timeout.', 'heading_path': ['Slide 2'], 'page_start': 1, 'page_end': 1},",
        "    ]",
        "default_dir = Path(tempfile.mkdtemp(prefix='kbprep-default-split-'))",
        "slide_dir = Path(tempfile.mkdtemp(prefix='kbprep-slide-split-'))",
        "split_into_chunks(blocks(), str(default_dir), 'pdf_like', 'abcdef1234567890', 'run-default')",
        "split_into_chunks(blocks(), str(slide_dir), 'pdf_like', 'abcdef1234567890', 'run-slide', split_strategy='preserve_slide_or_page_order')",
        "default_manifest = [json.loads(line) for line in (default_dir / 'chunk_manifest.jsonl').read_text(encoding='utf-8').splitlines()]",
        "slide_manifest = [json.loads(line) for line in (slide_dir / 'chunk_manifest.jsonl').read_text(encoding='utf-8').splitlines()]",
        "assert len(default_manifest) == 1, default_manifest",
        "assert [m['page_start'] for m in slide_manifest] == [0, 1], slide_manifest",
        "assert [m['page_end'] for m in slide_manifest] == [0, 1], slide_manifest",
        "assert all(m['split_strategy'] == 'preserve_slide_or_page_order' for m in slide_manifest), slide_manifest",
        "chunk_text = (slide_dir / 'chunks' / 'chunk_0001.md').read_text(encoding='utf-8')",
        "assert 'split_strategy: preserve_slide_or_page_order' in chunk_text",
      ].join("\n"),
      [],
    );
  });

  it("keeps shared format routing consistent across diagnose, prepare, detect, and batch", () => {
    runPython(
      [
        "from kbprep_worker.supported_formats import (",
        "    BATCH_SUPPORTED_EXTENSIONS, DIRECT_EXTENSIONS, FORMAT_BY_EXTENSION, MEDIA_EXTENSIONS, MINERU_EXTENSIONS,",
        "    CODE_EXTENSIONS, EPUB_EXTENSIONS, NOTEBOOK_EXTENSIONS, OFFICE_XML_EXTENSIONS, SOURCE_TYPE_BY_EXTENSION",
        ")",
        "from kbprep_worker import diagnose, detect, prepare, prepare_batch",
        "assert diagnose.EXTENSION_MAP is FORMAT_BY_EXTENSION",
        "assert prepare.DIRECT_EXTENSIONS is DIRECT_EXTENSIONS",
        "assert prepare.EPUB_EXTENSIONS is EPUB_EXTENSIONS",
        "assert prepare.MEDIA_EXTENSIONS is MEDIA_EXTENSIONS",
        "assert prepare.OFFICE_XML_EXTENSIONS is OFFICE_XML_EXTENSIONS",
        "assert prepare_batch.SUPPORTED_EXTENSIONS is BATCH_SUPPORTED_EXTENSIONS",
        "assert detect.EXTENSION_MAP is SOURCE_TYPE_BY_EXTENSION",
        "assert '.epub' in EPUB_EXTENSIONS",
        "assert '.epub' not in MINERU_EXTENSIONS",
        "assert '.py' in CODE_EXTENSIONS",
        "assert '.yaml' in CODE_EXTENSIONS",
        "assert '.ipynb' in NOTEBOOK_EXTENSIONS",
        "for ext in ['.json', '.html', '.csv', '.vtt', '.py', '.yaml', '.ipynb', '.docx', '.pptx', '.xlsx', '.epub']:",
        "    assert ext in FORMAT_BY_EXTENSION, ext",
        "    assert ext in BATCH_SUPPORTED_EXTENSIONS, ext",
        "for ext in ['.ogg', '.avi']:",
        "    assert ext in FORMAT_BY_EXTENSION, ext",
        "    assert ext in MEDIA_EXTENSIONS, ext",
        "    assert ext not in BATCH_SUPPORTED_EXTENSIONS, ext",
      ].join("\n"),
      [],
    );
  });

  it("returns a structured timeout error when MinerU conversion exceeds its subprocess budget", () => {
    runPython(
      [
        "import io, json, os, sys, tempfile",
        "from pathlib import Path",
        "from kbprep_worker import mineru_adapter, prepare",
        "root = Path(tempfile.mkdtemp(prefix='kbprep-timeout-'))",
        "input_path = root / 'slow.pdf'",
        "output_root = root / 'out'",
        "input_path.write_bytes(b'%PDF-1.4\\n% fake pdf for timeout path')",
        "os.environ['KBPREP_MINERU_TIMEOUT_SECONDS'] = '45'",
        "assert mineru_adapter.mineru_timeout_seconds() == 45",
        "def fake_run_mineru(**kwargs):",
        "    raise TimeoutError('MinerU timed out after 45s processing slow.pdf')",
        "mineru_adapter.run_mineru = fake_run_mineru",
        "stdout = io.StringIO()",
        "old_stdout = sys.stdout",
        "try:",
        "    sys.stdout = stdout",
        "    try:",
        "        prepare.run({",
        "        'input_path': str(input_path),",
        "        'output_root': str(output_root),",
        "        'profile': 'lite',",
        "        'mode': 'rules_only',",
        "        'language': 'zh',",
        "        'force': True,",
        "        })",
        "    except SystemExit as exc:",
        "        assert exc.code == 1, exc.code",
        "finally:",
        "    sys.stdout = old_stdout",
        "payload = json.loads(stdout.getvalue())",
        "assert payload['ok'] is False, payload",
        "assert payload['error']['code'] == 'E_TIMEOUT', payload",
        "details = payload['error']['details']",
        "assert details['mineru_timeout_seconds'] == 45, details",
        "error_report = Path(details['error_report'])",
        "assert error_report.exists(), details",
        "report = json.loads(error_report.read_text(encoding='utf-8'))",
        "assert report['code'] == 'E_TIMEOUT', report",
        "assert report['original_file'], report",
        "assert report['diagnosis']['detected_format'] == 'pdf', report",
      ].join("\n"),
      [],
    );
  });

  it("does not reuse an existing run created by a different runtime", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-runtime-cache-"));
    try {
      runPython(
        [
          "import json, sys",
          "from pathlib import Path",
          "from kbprep_worker.prepare import _find_existing_run",
          "root = Path(sys.argv[1])",
          "run_dir = root / 'runs' / 'old_run'",
          "run_dir.mkdir(parents=True, exist_ok=True)",
          "(run_dir / 'quality_report.json').write_text(json.dumps({",
          "    'source_sha256': 'abc',",
          "    'config_hash': 'cfg',",
          "    'plugin_version': '0.4.0',",
          "    'runtime_cache_key': 'cpu-runtime'",
          "}), encoding='utf-8')",
          "assert _find_existing_run(root, 'abc', 'cfg', '0.4.0', 'gpu-runtime') is None",
          "match = _find_existing_run(root, 'abc', 'cfg', '0.4.0', 'cpu-runtime')",
          "assert match and match['run_id'] == 'old_run'",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("excludes image-only evidence from text coverage gates", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'images').mkdir()",
        "(run_dir / 'images' / 'a.jpg').write_bytes(b'fake')",
        "(run_dir / 'images' / 'b.jpg').write_bytes(b'fake')",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落。' * 80, encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'b1', 'status': 'keep', 'type': 'paragraph', 'text': '正文知识段落。' * 80},",
        "  {'block_id': 'b2', 'status': 'review', 'type': 'image_evidence', 'text': '![](images/a.jpg)'},",
        "  {'block_id': 'b3', 'status': 'evidence', 'type': 'image_evidence', 'text': '![](images/b.jpg)'},",
        "  {'block_id': 'b4', 'status': 'discard', 'type': 'marketing_cta', 'text': '扫码入群领取体验卡'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'pdf_like', {'file_id': 'test'})",
        "assert report['coverage_excluded_blocks'] == 3",
        "assert report['coverage_ratio'] > 0.95",
        "assert report['discard_ratio_excluded_blocks'] == 3",
        "assert report['retention']['image_total'] == 2",
        "assert report['retention']['image_review'] == 1",
        "assert report['retention']['image_evidence'] == 1",
        "assert report['retention']['image_missing_files'] == 0",
        "assert report['image_retention']['referenced_file_count'] == 2",
        "assert not any('coverage' in err for err in report['strict_errors']), report",
        "assert not any('image files are missing' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("reports concrete detail retention and fails when detail-bearing blocks are discarded", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'step1', 'status': 'keep', 'type': 'operation_step', 'text': '步骤1：打开平台后台，设置 threshold=0.82。', 'protected': True},",
        "  {'block_id': 'link1', 'status': 'keep', 'type': 'tool_instruction', 'text': '工具地址：https://example.com/docs，账号角色选择 editor。', 'protected': True},",
        "  {'block_id': 'prompt1', 'status': 'keep', 'type': 'prompt', 'text': 'Prompt：请逐段保留操作步骤，不要总结。', 'protected': True},",
        "  {'block_id': 'code1', 'status': 'keep', 'type': 'code', 'text': '```python\\nprint(42)\\n```', 'protected': True},",
        "  {'block_id': 'table1', 'status': 'keep', 'type': 'table', 'text': '| 字段 | 值 |\\n| --- | --- |\\n| retry_count | 3 |', 'protected': True},",
        "  {'block_id': 'bad1', 'status': 'discard', 'type': 'paragraph', 'text': '失败经验：当 retry_count=3 仍失败时，记录 failure_reason 并人工复查。'},",
        "  {'block_id': 'cta1', 'status': 'discard', 'type': 'marketing_cta', 'text': '扫码入群领取体验卡'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'detail-test'})",
        "detail = report['detail_retention']",
        "assert detail['operation_step']['total_blocks'] == 1, detail",
        "assert detail['tool_or_platform']['total_blocks'] == 2, detail",
        "assert detail['parameter']['total_blocks'] == 3, detail",
        "assert detail['link']['total_blocks'] == 1, detail",
        "assert detail['prompt']['discarded_blocks'] == 0, detail",
        "assert detail['code']['discarded_blocks'] == 0, detail",
        "assert detail['table']['discarded_blocks'] == 0, detail",
        "assert detail['discarded_detail_block_ids'] == ['bad1'], detail",
        "assert any('detail-bearing blocks were discarded' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("fails quality when cleaned markdown drops signals from kept detail blocks", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('# 操作流程\\n\\n步骤1：打开后台。\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'step1', 'status': 'keep', 'type': 'operation_step', 'text': '步骤1：打开后台，设置 threshold=0.82，并访问 https://example.com/config。', 'protected': True},",
        "  {'block_id': 'code1', 'status': 'keep', 'type': 'code', 'text': '```python\\nretry_count = 3\\nfailure_reason = \"timeout\"\\n```', 'protected': True},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'output-retention-test'})",
        "retention = report['output_retention']",
        "assert retention['link']['missing'] == ['https://example.com/config'], retention",
        "assert 'threshold=0.82' in retention['parameter']['missing'], retention",
        "assert retention['code']['missing_count'] == 1, retention",
        "assert any('kept detail signals missing from cleaned.md' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("checks review and evidence detail signals against their own output files", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "(run_dir / 'evidence').mkdir()",
        "(run_dir / 'cleaned.md').write_text('# 正文\\n\\n步骤1：设置 threshold=0.82。\\n', encoding='utf-8')",
        "(run_dir / 'review_needed.md').write_text('需要复查：https://example.com/review retry_count=3\\n', encoding='utf-8')",
        "(run_dir / 'evidence' / 'marketing_pages.md').write_text('证据链接：https://example.com/evidence\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'keep1', 'status': 'keep', 'type': 'operation_step', 'text': '步骤1：设置 threshold=0.82。', 'protected': True},",
        "  {'block_id': 'review1', 'status': 'review', 'type': 'paragraph', 'text': '需要复查：https://example.com/review retry_count=3', 'protected': False},",
        "  {'block_id': 'evidence1', 'status': 'evidence', 'type': 'community_benefit', 'text': '证据链接：https://example.com/evidence', 'protected': False},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'destination-retention-test'})",
        "retention = report['output_retention']",
        "assert retention['cleaned_md']['missing_total'] == 0, retention",
        "assert retention['review_needed_md']['missing_total'] == 0, retention",
        "assert retention['evidence_md']['missing_total'] == 0, retention",
        "assert retention['missing_total'] == 0, retention",
        "assert not any('kept detail signals missing from cleaned.md' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("keeps internal PDF page markers out of readable markdown outputs", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "from kbprep_worker.render_outputs import render",
        "with TemporaryDirectory() as tmp:",
        "    run_dir = Path(tmp)",
        "    blocks = [",
        "        {'block_id': 'p1', 'status': 'keep', 'type': 'paragraph', 'text': '<!-- page: 1 -->', 'heading_path': [], 'page_start': 0, 'page_end': 0},",
        "        {'block_id': 'b1', 'status': 'keep', 'type': 'paragraph', 'text': '第一步：打开 OpenClaw 后台，设置 threshold=0.8。', 'heading_path': [], 'page_start': 0, 'page_end': 0},",
        "        {'block_id': 'p2', 'status': 'keep', 'type': 'paragraph', 'text': '<!-- page: 2 -->', 'heading_path': [], 'page_start': 1, 'page_end': 1},",
        "        {'block_id': 'b2', 'status': 'keep', 'type': 'paragraph', 'text': '第二步：记录 failure_reason=timeout，并保留 retry_count=3。' * 260, 'heading_path': [], 'page_start': 1, 'page_end': 1},",
        "    ]",
        "    render(blocks, str(run_dir), 'sha', 'run')",
        "    cleaned = (run_dir / 'cleaned.md').read_text(encoding='utf-8')",
        "    assert '<!-- page:' not in cleaned, cleaned[:300]",
        "    assert 'threshold=0.8' in cleaned, cleaned",
        "    assert 'retry_count=3' in cleaned, cleaned",
        "    part_text = '\\n'.join(p.read_text(encoding='utf-8') for p in sorted((run_dir / 'parts').glob('part_*.md')))",
        "    assert '<!-- page:' not in part_text, part_text[:300]",
      ].join("\n"),
      [],
    );
  });

  it("splits obvious promotional lines out of otherwise useful source blocks", () => {
    runPython(
      [
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.quality import _detail_retention_stats",
        "blocks = [",
        "  {",
        "    'block_id': 'cover1',",
        "    'status': 'keep',",
        "    'type': 'paragraph',",
        "    'text': '\\n'.join([",
        "      '信息来源：OpenClaw 官方文档 · GitHub 仓库 · 社区调研文档版本：v1.1.0',",
        "      '如有勘误或建议，欢迎关注公众号「花叔」反馈交流。',",
        "      '配套视频教程：B站「OpenClaw从0到1」 · 后续更新：飞书文档',",
        "      '第一步：打开 OpenClaw 后台，设置 threshold=0.8。',",
        "    ]),",
        "    'heading_path': [], 'page_start': 0, 'page_end': 0, 'risk_tags': [], 'protected': False,",
        "  },",
        "]",
        "cleaned = apply_clean_rules(blocks)",
        "kept = next(b for b in cleaned if b['block_id'] == 'cover1')",
        "discarded = [b for b in cleaned if b.get('status') == 'discard']",
        "assert '信息来源：OpenClaw 官方文档' in kept['text'], kept",
        "assert 'threshold=0.8' in kept['text'], kept",
        "assert '欢迎关注公众号' not in kept['text'], kept",
        "assert '配套视频教程' not in kept['text'], kept",
        "assert len(discarded) == 2, discarded",
        "assert all(b['type'] == 'marketing_cta' for b in discarded), discarded",
        "assert '欢迎关注公众号' in discarded[0]['text'], discarded",
        "assert '配套视频教程' in discarded[1]['text'], discarded",
        "stats = _detail_retention_stats(cleaned)",
        "assert stats['discarded_detail_block_ids'] == [], stats",
      ].join("\n"),
      [],
    );
  });

  it("accepts UTF-8 BOM JSON stdin from Windows shells", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const envelope = runWorkerRawInput(
        "diagnose",
        `\ufeff${JSON.stringify({ input_path: path.join(repoRoot, "README.md"), output_root: root })}`,
      );

      expect(envelope.ok).toBe(true);
      expect(envelope.data.detected_format).toBe("markdown");
      expect(envelope.data.source_type).toBe("markdown_note");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("detects broad source families from the shared format table", () => {
    runPython(
      [
        "from kbprep_worker.detect import detect_source_family, detect_source_type",
        "assert detect_source_type('notes.md') == 'markdown_note'",
        "assert detect_source_type('lesson.srt') == 'subtitle_transcript'",
        "assert detect_source_type('analysis.ipynb') == 'generic_block'",
        "assert detect_source_family('analysis.ipynb') == 'notebook'",
        "assert detect_source_family('script.py') == 'code'",
        "assert detect_source_family('book.epub') == 'ebook'",
        "assert detect_source_family('slides.pptx') == 'presentation'",
        "assert detect_source_family('clip.mp4') == 'video'",
      ].join("\n"),
      [],
    );
  });

  it("classifies long heading-rich documents with colon lines as reports, not transcripts", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const sourcePath = path.join(root, "technical-manual.md");
      const sections = Array.from({ length: 12 }, (_, index) => [
        `# 第${index + 1}章 配置说明`,
        "",
        "模型名称： gpt-4.1-mini",
        "参数 threshold： 0.8",
        "失败原因： 需要记录原始错误，不要总结掉。",
        "操作步骤： 打开后台，选择项目，填写参数，保存配置。",
        "注意事项： 如果接口返回 429，需要等待并重试。",
        "",
        "这是一段正文，用来描述章节里的知识背景、限制条件、案例过程和复盘细节。".repeat(60),
      ].join("\n"));
      writeFileSync(sourcePath, sections.join("\n\n"), "utf8");

      const envelope = runWorker("diagnose", {
        input_path: sourcePath,
        output_root: root,
        source_type: "auto",
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.heading_count).toBeGreaterThanOrEqual(12);
      expect(envelope.data.speaker_line_count).toBeGreaterThanOrEqual(8);
      expect(envelope.data.text_profile).toBe("ebook_or_long_report");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps tutorial steps that mention CTA phrases as policy examples", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "tutorial.md");
      writeFileSync(
        sourcePath,
        [
          "# 小红书账号规则教程",
          "",
          "第一步：检查文案里是否出现“扫码加入社群”。如果是在讲平台规则或违规案例，这句话必须保留，因为它是判断标准，不是广告。",
          "",
          "第二步：把检测结果记录到字段 risk_label，并把参数 threshold 设置为 0.8，方便后续复盘误判原因。",
          "",
          "第三步：只删除真正的购买引导、体验卡和无关广告，不要删除案例里的平台、账号、社群、引流等词。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_plus_review_pack",
        language: "zh",
        force: true,
      });

      const runDir = envelope.data.run_dir;
      const cleaned = readFileSync(path.join(runDir, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(runDir, "discarded.md"), "utf8");
      const conversionReport = JSON.parse(readFileSync(path.join(runDir, "conversion_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(conversionReport.runtime.python_executable).toContain("python");
      expect(conversionReport.runtime).toHaveProperty("mineru_path");
      expect(conversionReport.runtime).toHaveProperty("torch_cuda_available");
      expect(conversionReport.runtime).toHaveProperty("mineru_device");
      expect(existsSync(path.join(outputRoot, "converted.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "blocks.jsonl"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "cleaned.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "discarded.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "review_needed.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "quality_report.json"))).toBe(true);
      expect(cleaned).toContain("讲平台规则或违规案例");
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).not.toContain("领取体验卡");
      expect(discarded).toContain("领取体验卡");
      expect(discarded).not.toContain("讲平台规则或违规案例");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("cleans real Chinese CTA while preserving tutorial context", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-real-zh-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "tutorial.md");
      writeFileSync(
        sourcePath,
        [
          "# 小红书账号规则教程",
          "",
          "第一步：检查文案里是否出现“扫码加入社群”。如果是在讲平台规则或违规案例，这句话必须保留，因为它是判断标准，不是广告。",
          "",
          "第二步：把检测结果记录到字段 risk_label，并把参数 threshold 设置为 0.8，方便后续复盘误判原因。",
          "",
          "扫码入群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const runDir = envelope.data.run_dir;
      const cleaned = readFileSync(path.join(runDir, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(runDir, "discarded.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(runDir, "quality_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(quality.strict_errors).toEqual([]);
      expect(cleaned).toContain("讲平台规则或违规案例");
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).not.toContain("扫码入群领取体验卡");
      expect(discarded).toContain("扫码入群领取体验卡");
      expect(discarded).not.toContain("讲平台规则或违规案例");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps cleanup-analysis paragraphs that mention QR or CTA pollution", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-cleanup-analysis-"));
    try {
      const inputPath = path.join(root, "analysis.md");
      const outputRoot = path.join(root, "out");
      writeFileSync(
        inputPath,
        [
          "# 清洗复盘",
          "",
          "当前清洗版的问题之一，是图片几乎没有进入清洗范围，所以营销图和二维码图仍然可能留在 `cleaned.md`。这句话是正文分析，不能当广告删除。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        force: true,
        language: "zh",
        source_type: "auto",
        splitter: "auto",
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("二维码图仍然可能留在 `cleaned.md`");
      expect(discarded).toContain("扫码加入社群领取体验卡");
      expect(discarded).not.toContain("二维码图仍然可能留在 `cleaned.md`");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("keeps short unnumbered case details that mention CTA phrases", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-case-cta-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      const sourcePath = path.join(inputDir, "case.md");
      writeFileSync(
        sourcePath,
        [
          "# 小红书账号违规案例拆解",
          "",
          "案例：这个账号在主页写“扫码加入社群领取体验卡”，被平台判定为引流违规；处理方式是删除主页广告语，并记录 risk_label=引流违规。",
          "",
          "判断标准：如果这句话出现在案例复盘里，要保留完整上下文、处理动作和字段值，不能只因为出现扫码、社群、体验卡就删除。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        source_type: "auto",
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const blocks = readFileSync(path.join(outputRoot, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const caseBlock = blocks.find((block) => block.text.includes("risk_label=引流违规"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("主页写“扫码加入社群领取体验卡”");
      expect(cleaned).toContain("risk_label=引流违规");
      expect(discarded).toContain("扫码加入社群领取体验卡。");
      expect(discarded).not.toContain("risk_label=引流违规");
      expect(caseBlock.status).toBe("keep");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps platform and conversion terms when they are report body, not CTA", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "report.md");
      writeFileSync(
        sourcePath,
        [
          "# AI 美妆社媒营销新赛道",
          "",
          "微信小程序可承接肤质诊断和会员复购提醒。",
          "",
          "转化层面：通过诊断结果直接关联产品组合推荐，实现“诊-购”一体化。",
          "",
          "引流层面：与平台合作，打造 AR 试妆滤镜，降低尝新门槛。",
          "",
          "喜欢在抖音/小红书玩“AI换脸试妆挑战”等互动玩法。",
          "",
          "扫码加入AI创业营社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const runDir = envelope.data.run_dir;
      const cleaned = readFileSync(path.join(runDir, "cleaned.md"), "utf8");
      const reviewNeeded = readFileSync(path.join(runDir, "review_needed.md"), "utf8");
      const discarded = readFileSync(path.join(runDir, "discarded.md"), "utf8");

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("微信小程序可承接肤质诊断");
      expect(cleaned).toContain("转化层面：通过诊断结果");
      expect(cleaned).toContain("引流层面：与平台合作");
      expect(cleaned).toContain("抖音/小红书");
      expect(reviewNeeded).not.toContain("微信小程序可承接肤质诊断");
      expect(reviewNeeded).not.toContain("转化层面：通过诊断结果");
      expect(discarded).toContain("扫码加入AI创业营社群领取体验卡");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("normalizes local subtitle files into readable transcript markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.srt");
      writeFileSync(
        sourcePath,
        [
          "1",
          "00:00:01,000 --> 00:00:04,000",
          "第一步：打开后台，把参数 threshold 设置为 0.8。",
          "",
          "2",
          "00:00:05,000 --> 00:00:08,000",
          "第二步：记录失败原因，不要把细节总结掉。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const converted = readFileSync(path.join(envelope.data.run_dir, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");

      expect(envelope.data.strict_errors).toEqual([]);
      expect(converted).toContain("# Transcript");
      expect(converted).not.toContain("-->");
      expect(converted).not.toContain("00:00:01,000");
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).toContain("不要把细节总结掉");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("removes pure transcript filler while keeping steps and experience details", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-transcript-filler-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "talk.srt");
      writeFileSync(
        sourcePath,
        [
          "1",
          "00:00:01,000 --> 00:00:02,000",
          "大家好",
          "",
          "2",
          "00:00:03,000 --> 00:00:07,000",
          "第一步：打开后台，把 threshold 设置为 0.8，并记录失败原因。",
          "",
          "3",
          "00:00:08,000 --> 00:00:12,000",
          "我踩过一个坑：不要把平台规则里的扫码案例直接删掉。",
          "",
          "4",
          "00:00:13,000 --> 00:00:15,000",
          "记得点赞关注",
          "",
          "5",
          "00:00:16,000 --> 00:00:17,000",
          "下期见",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).toContain("我踩过一个坑");
      expect(cleaned).not.toContain("大家好");
      expect(cleaned).not.toContain("点赞关注");
      expect(cleaned).not.toContain("下期见");
      expect(discarded).toContain("大家好");
      expect(discarded).toContain("点赞关注");
      expect(discarded).toContain("下期见");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("removes English transcript filler while keeping tutorial details", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-english-transcript-filler-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.srt");
      writeFileSync(
        sourcePath,
        [
          "1",
          "00:00:01,000 --> 00:00:02,000",
          "Hey guys",
          "",
          "2",
          "00:00:03,000 --> 00:00:06,000",
          "Step 1: open the dashboard and set threshold=0.8.",
          "",
          "3",
          "00:00:07,000 --> 00:00:11,000",
          "My failure lesson: keep failure_reason=timeout and retry_count=3 for review.",
          "",
          "4",
          "00:00:12,000 --> 00:00:14,000",
          "Don't forget to like and subscribe",
          "",
          "5",
          "00:00:15,000 --> 00:00:16,000",
          "Thanks for watching",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "en",
        force: true,
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("Step 1: open the dashboard");
      expect(cleaned).toContain("threshold=0.8");
      expect(cleaned).toContain("failure_reason=timeout");
      expect(cleaned).toContain("retry_count=3");
      expect(cleaned).not.toContain("Hey guys");
      expect(cleaned).not.toContain("like and subscribe");
      expect(cleaned).not.toContain("Thanks for watching");
      expect(discarded).toContain("Hey guys");
      expect(discarded).toContain("like and subscribe");
      expect(discarded).toContain("Thanks for watching");
      expect(quality.detail_retention.operation_step.total_blocks).toBeGreaterThanOrEqual(1);
      expect(quality.output_retention.cleaned_md.parameter.missing_count).toBe(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("treats English Step N tutorial lines as protected operation steps", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-english-steps-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.txt");
      writeFileSync(
        sourcePath,
        [
          "Step 1: open dashboard",
          "",
          "Set threshold=0.8 and record failure_reason=timeout.",
          "",
          "Step 2: export the result and keep retry_count=3 in the notes.",
        ].join("\n"),
        "utf8",
      );

      const diagnosis = runWorker("diagnose", {
        input_path: sourcePath,
        output_root: outputRoot,
        source_type: "auto",
      });
      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "en",
        force: true,
      });

      const blocks = readFileSync(path.join(outputRoot, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");

      expect(diagnosis.data.text_profile).toBe("tutorial");
      expect(envelope.data.strict_errors).toEqual([]);
      expect(blocks.filter((block) => block.type === "operation_step").length).toBeGreaterThanOrEqual(2);
      expect(quality.retention.operation_step_total).toBeGreaterThanOrEqual(2);
      expect(quality.detail_retention.operation_step.total_blocks).toBeGreaterThanOrEqual(2);
      expect(cleaned).toContain("Step 1: open dashboard");
      expect(cleaned).toContain("retry_count=3");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("preserves Obsidian markdown structure while removing standalone CTA pollution", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-obsidian-md-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "obsidian-note.md");
      writeFileSync(
        sourcePath,
        [
          "---",
          "tags: [kbprep, tutorial]",
          "aliases:",
          "  - 清洗插件测试",
          "---",
          "",
          "# Obsidian 清洗教程",
          "",
          "[[OpenClaw]] 和 [[MinerU]] 都要保留，因为它们是工具链细节。 #LLM-Wiki",
          "",
          "> [!warning] CTA 判断规则",
          "> 如果教程案例里出现“扫码入群”，不要按关键词删除；要记录 risk_label=possible_cta，并保留上下文。",
          "",
          "步骤1：打开插件输出目录，检查 cleaned.md、discarded.md、review_needed.md。",
          "",
          "扫码加入社群领取体验卡",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("tags: [kbprep, tutorial]");
      expect(cleaned).toContain("aliases:");
      expect(cleaned).toContain("[[OpenClaw]]");
      expect(cleaned).toContain("[[MinerU]]");
      expect(cleaned).toContain("#LLM-Wiki");
      expect(cleaned).toContain("> [!warning] CTA 判断规则");
      expect(cleaned).toContain("risk_label=possible_cta");
      expect(cleaned).toContain("步骤1：打开插件输出目录");
      expect(cleaned).not.toContain("扫码加入社群领取体验卡");
      expect(discarded).toContain("扫码加入社群领取体验卡");
      expect(quality.detail_retention.operation_step.total_blocks).toBeGreaterThanOrEqual(1);
      expect(quality.output_retention.cleaned_md.parameter.missing_count).toBe(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("converts local HTML, JSON, and CSV sources into readable Markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-direct-formats-"));
    try {
      const inputDir = path.join(root, "input");
      mkdirSync(inputDir);
      const htmlAssetsDir = path.join(inputDir, "html-assets");
      mkdirSync(htmlAssetsDir);
      const png1x1 = Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
        "base64",
      );
      writeFileSync(path.join(htmlAssetsDir, "step.png"), png1x1);

      const htmlPath = path.join(inputDir, "saved-page.html");
      const htmlOut = path.join(root, "html-out");
      writeFileSync(
        htmlPath,
        [
          "<html><head><style>.ad{display:none}</style><script>alert('x')</script></head>",
          "<p>工具地址：<a href=\"https://example.com/tool?mode=kbprep\">打开工具</a></p>",
          "<p><img src=\"html-assets/step.png\" alt=\"后台截图\"></p>",
          "<body><nav>扫码入群领取体验卡</nav><article>",
          "<h1>操作教程</h1><p>第一步：打开平台后台，设置 threshold=0.8。</p>",
          "<ul><li>保留工具名、参数和失败原因。</li></ul>",
          "</article></body></html>",
        ].join(""),
        "utf8",
      );

      const htmlDiagnosis = runWorker("diagnose", {
        input_path: htmlPath,
        output_root: htmlOut,
        source_type: "auto",
      });
      expect(htmlDiagnosis.data.detected_format).toBe("html");
      expect(htmlDiagnosis.data.recommended_pipeline).toBe("direct");
      expect(htmlDiagnosis.data.conversion_strategy).toBe("direct");
      expect(htmlDiagnosis.data.text_profile).toBe("tutorial");

      const htmlEnvelope = runWorker("prepare", {
        input_path: htmlPath,
        output_root: htmlOut,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const htmlConverted = readFileSync(path.join(htmlEnvelope.data.run_dir, "converted.md"), "utf8");
      expect(htmlEnvelope.data.strict_errors).toEqual([]);
      expect(htmlConverted).toContain("# 操作教程");
      expect(htmlConverted).toContain("threshold=0.8");
      expect(htmlConverted).toContain("[打开工具](https://example.com/tool?mode=kbprep)");
      expect(htmlConverted).toContain("![后台截图](images/html-assets/step.png)");
      expect(htmlConverted).toContain("- 保留工具名、参数和失败原因。");
      expect(htmlConverted).not.toContain("<script>");
      expect(existsSync(path.join(htmlOut, "images", "html-assets", "step.png"))).toBe(true);
      expect(htmlConverted).not.toContain("扫码入群领取体验卡");

      const jsonPath = path.join(inputDir, "config.json");
      const jsonOut = path.join(root, "json-out");
      writeFileSync(jsonPath, JSON.stringify({ tool: "kbprep", threshold: 0.8, steps: ["detect", "clean"] }), "utf8");
      const jsonDiagnosis = runWorker("diagnose", {
        input_path: jsonPath,
        output_root: jsonOut,
        source_type: "auto",
      });
      expect(jsonDiagnosis.data.detected_format).toBe("json");
      expect(jsonDiagnosis.data.recommended_pipeline).toBe("direct");
      expect(jsonDiagnosis.data.conversion_strategy).toBe("direct");

      const jsonEnvelope = runWorker("prepare", {
        input_path: jsonPath,
        output_root: jsonOut,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const jsonConverted = readFileSync(path.join(jsonEnvelope.data.run_dir, "converted.md"), "utf8");
      expect(jsonEnvelope.data.strict_errors).toEqual([]);
      expect(jsonConverted).toContain("```json");
      expect(jsonConverted).toContain('"threshold": 0.8');

      const csvPath = path.join(inputDir, "table.csv");
      const csvOut = path.join(root, "csv-out");
      writeFileSync(csvPath, "步骤,参数,说明\n第一步,threshold=0.8,保留失败原因\n", "utf8");
      const csvDiagnosis = runWorker("diagnose", {
        input_path: csvPath,
        output_root: csvOut,
        source_type: "auto",
      });
      expect(csvDiagnosis.data.detected_format).toBe("text");
      expect(csvDiagnosis.data.recommended_pipeline).toBe("direct");
      expect(csvDiagnosis.data.conversion_strategy).toBe("direct");

      const csvEnvelope = runWorker("prepare", {
        input_path: csvPath,
        output_root: csvOut,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const csvConverted = readFileSync(path.join(csvEnvelope.data.run_dir, "converted.md"), "utf8");
      expect(csvEnvelope.data.strict_errors).toEqual([]);
      expect(csvConverted).toContain("| 步骤 | 参数 | 说明 |");
      expect(csvConverted).toContain("| 第一步 | threshold=0.8 | 保留失败原因 |");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("converts GitHub-style source and config files as fenced Markdown without summarizing code", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-code-source-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "workflow.py");
      writeFileSync(
        sourcePath,
        [
          "# GitHub example workflow",
          "CONFIG_URL = 'https://example.com/config'",
          "threshold = 0.82",
          "retry_count = 3",
          "",
          "def run_job(item):",
          "    if item.get('failed'):",
          "        failure_reason = 'timeout'",
          "        return {'status': 'review', 'failure_reason': failure_reason}",
          "    return {'status': 'keep'}",
        ].join("\n"),
        "utf8",
      );

      const diagnosis = runWorker("diagnose", {
        input_path: sourcePath,
        output_root: outputRoot,
        source_type: "auto",
      });
      expect(diagnosis.ok).toBe(true);
      expect(diagnosis.data.detected_format).toBe("code");
      expect(diagnosis.data.source_type).toBe("generic_block");
      expect(diagnosis.data.recommended_pipeline).toBe("direct");
      expect(diagnosis.data.conversion_strategy).toBe("direct_code");

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      expect(prepared.ok).toBe(true);

      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));

      expect(converted).toContain("```python");
      expect(converted).toContain("CONFIG_URL = 'https://example.com/config'");
      expect(converted).toContain("failure_reason = 'timeout'");
      expect(cleaned).toContain("retry_count = 3");
      expect(cleaned).toContain("return {'status': 'review'");
      expect(quality.strict_errors).toEqual([]);
      expect(quality.detail_retention.code.total_blocks).toBeGreaterThan(0);
      expect(quality.detail_retention.parameter.total_blocks).toBeGreaterThan(0);
      expect(quality.detail_retention.link.total_blocks).toBeGreaterThan(0);
      expect(conversionReport.converter).toBe("direct_code");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("converts Jupyter notebooks into readable Markdown cells with code and text outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-notebook-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const notebookPath = path.join(inputDir, "tutorial.ipynb");
      writeFileSync(
        notebookPath,
        JSON.stringify({
          cells: [
            {
              cell_type: "markdown",
              source: ["# Notebook 教程\n", "步骤1：配置 threshold=0.82，参考 https://example.com/notebook\n"],
            },
            {
              cell_type: "code",
              source: ["retry_count = 3\n", "failure_reason = 'timeout'\n", "print(failure_reason)\n"],
              outputs: [
                { output_type: "stream", name: "stdout", text: ["timeout\n"] },
                { output_type: "execute_result", data: { "text/plain": ["{'status': 'review'}"] } },
              ],
            },
          ],
          metadata: { kernelspec: { language: "python", name: "python3" } },
          nbformat: 4,
          nbformat_minor: 5,
        }),
        "utf8",
      );

      const diagnosis = runWorker("diagnose", {
        input_path: notebookPath,
        output_root: outputRoot,
        source_type: "auto",
      });
      expect(diagnosis.ok).toBe(true);
      expect(diagnosis.data.detected_format).toBe("notebook");
      expect(diagnosis.data.recommended_pipeline).toBe("direct");
      expect(diagnosis.data.conversion_strategy).toBe("notebook_json");

      const prepared = runWorker("prepare", {
        input_path: notebookPath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      expect(prepared.ok).toBe(true);

      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));

      expect(converted).toContain("# Notebook 教程");
      expect(converted).toContain("```python");
      expect(converted).toContain("retry_count = 3");
      expect(converted).toContain("## Cell 2 Output");
      expect(converted).toContain("timeout");
      expect(converted).toContain("{'status': 'review'}");
      expect(cleaned).toContain("failure_reason = 'timeout'");
      expect(quality.strict_errors).toEqual([]);
      expect(quality.detail_retention.parameter.total_blocks).toBeGreaterThan(0);
      expect(quality.output_retention.cleaned_md.parameter.missing_count).toBe(0);
      expect(conversionReport.converter).toBe("notebook_json");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("converts modern Office files through the local XML fallback when MinerU is unnecessary", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-office-"));
    try {
      const inputDir = path.join(root, "input");
      mkdirSync(inputDir);
      const docxPath = path.join(inputDir, "tutorial.docx");
      const pptxPath = path.join(inputDir, "slides.pptx");
      const xlsxPath = path.join(inputDir, "params.xlsx");
      makeOfficeFixtures(docxPath, pptxPath, xlsxPath);

      const cases = [
        {
          input: docxPath,
          out: path.join(root, "docx-out"),
          format: "docx",
          expected: ["# DOCX Tutorial", "threshold=0.8", "| Field | Value |", "| retry_count | 3 |"],
        },
        {
          input: pptxPath,
          out: path.join(root, "pptx-out"),
          format: "pptx",
          expected: [
            "# Slide 1: PPT Tutorial Slide",
            "failure_reason=timeout",
            "![Slide 1 Image 1](images/office/slide_001/step.png)",
            "# Slide 2: PPT Case Slide",
            "retry_count=3",
          ],
        },
        {
          input: xlsxPath,
          out: path.join(root, "xlsx-out"),
          format: "xlsx",
          expected: ["# Params", "| Name | Value |", "| threshold | 0.8 |"],
        },
      ];

      for (const item of cases) {
        const diagnosis = runWorker("diagnose", {
          input_path: item.input,
          output_root: item.out,
          source_type: "auto",
        });
        expect(diagnosis.data.detected_format).toBe(item.format);
        expect(diagnosis.data.recommended_pipeline).toBe("office_xml");
        expect(diagnosis.data.conversion_strategy).toBe("office_xml");

        const envelope = runWorker("prepare", {
          input_path: item.input,
          output_root: item.out,
          profile: "tutorial",
          mode: "rules_only",
          language: "zh",
          force: true,
        });
        const converted = readFileSync(path.join(envelope.data.run_dir, "converted.md"), "utf8");
        const cleaned = readFileSync(path.join(envelope.data.run_dir, "cleaned.md"), "utf8");
        const diagnosisReport = JSON.parse(readFileSync(path.join(envelope.data.run_dir, "diagnosis_report.json"), "utf8"));
        const conversionReport = JSON.parse(readFileSync(path.join(envelope.data.run_dir, "conversion_report.json"), "utf8"));

        expect(envelope.data.strict_errors).toEqual([]);
        expect(envelope.data.outputs.diagnosis_report).toContain("diagnosis_report.json");
        expect(envelope.data.latest_outputs.diagnosis_report).toContain("diagnosis_report.json");
        expect(diagnosisReport.schema).toBe("kbprep.diagnosis_report.v1");
        expect(diagnosisReport.detected_format).toBe(item.format);
        expect(diagnosisReport.recommended_pipeline).toBe("office_xml");
        expect(conversionReport.converter).toBe("office_xml");
        expect(conversionReport.diagnosed_format).toBe(item.format);
        expect(conversionReport.diagnosed_pipeline).toBe("office_xml");
        expect(conversionReport.diagnosed_strategy).toBe("office_xml");
        if (item.format === "pptx") {
          expect(conversionReport.diagnosed_split_strategy).toBe("preserve_slide_or_page_order");
          expect(conversionReport.mineru_artifacts.content_list_path).toContain("pptx_content_list.json");
          const manifest = readFileSync(path.join(envelope.data.run_dir, "chunk_manifest.jsonl"), "utf8")
            .trim()
            .split(/\r?\n/)
            .map((line) => JSON.parse(line));
          expect(manifest.map((entry) => entry.split_strategy)).toContain("preserve_slide_or_page_order");
          expect(manifest.some((entry) => entry.page_start === 0)).toBe(true);
          expect(manifest.some((entry) => entry.page_start === 1)).toBe(true);
          expect(conversionReport.mineru_artifacts.office_image_assets.copied_count).toBe(1);
          expect(existsSync(path.join(item.out, "images", "office", "slide_001", "step.png"))).toBe(true);
        }
        for (const expected of item.expected) {
          expect(converted).toContain(expected);
          expect(cleaned).toContain(expected);
        }
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("converts EPUB ebooks through local XHTML extraction instead of MinerU", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-epub-"));
    try {
      const inputDir = path.join(root, "input");
      mkdirSync(inputDir);
      const epubPath = path.join(inputDir, "tutorial.epub");
      const outputRoot = path.join(root, "output");
      makeEpubFixture(epubPath);

      const diagnosis = runWorker("diagnose", {
        input_path: epubPath,
        output_root: outputRoot,
        source_type: "auto",
      });
      expect(diagnosis.data.detected_format).toBe("ebook");
      expect(diagnosis.data.recommended_pipeline).toBe("epub_xhtml");
      expect(diagnosis.data.conversion_strategy).toBe("epub_xhtml");

      const envelope = runWorker("prepare", {
        input_path: epubPath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        source_type: "auto",
        force: true,
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.strict_errors).toEqual([]);
      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));

      expect(conversionReport.converter).toBe("epub_xhtml");
      expect(conversionReport.diagnosed_strategy).toBe("epub_xhtml");
      expect(converted.indexOf("# 第一章 工具准备")).toBeLessThan(converted.indexOf("# 第二章 案例复盘"));
      expect(cleaned).toContain("threshold=0.8");
      expect(cleaned).toContain("failure_reason=timeout");
      expect(cleaned).toContain("retry_count=3");
      expect(cleaned).not.toContain("扫码加入社群领取体验卡");
      expect(discarded).toContain("扫码加入社群领取体验卡");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("converts trusted text-layer PDFs without invoking MinerU", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-pdf-text-"));
    try {
      const inputPath = path.join(root, "tutorial.pdf");
      const outputRoot = path.join(root, "output");
      makeTextLayerPdf(inputPath);

      const envelope = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        source_type: "auto",
        force: true,
      });

      expect(envelope.ok).toBe(true);
      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      expect(converted).toContain("Step 1: open settings and set threshold to 0.8.");
      expect(converted).toContain("retry_count values");

      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));
      expect(conversionReport.converter).toBe("pdf_text_layer");
      expect(conversionReport.diagnosed_strategy).toBe("pdf_text_layer");
      expect(conversionReport.mineru_artifacts.source_md_path).toContain("converted.md");
      expect(conversionReport.mineru_artifacts.content_list_path).toContain("pdf_text_content_list.json");

      const blocks = readFileSync(path.join(outputRoot, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const stepBlock = blocks.find((block) => block.text.includes("threshold to 0.8"));
      expect(stepBlock.page_start).toBe(0);
      expect(stepBlock.page_end).toBe(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 10_000);

  it("falls back to MinerU when a trusted PDF text-layer conversion produces unreadable Markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-pdf-fallback-"));
    try {
      const inputPath = path.join(root, "tutorial.pdf");
      const outputRoot = path.join(root, "output");
      makeTextLayerPdf(inputPath);

      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter, pdf_text, prepare",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "calls = []",
          "def bad_text_layer(input_path, output_path, run_dir):",
          "    output_path.write_text(('Ჭ䌦圳➉ᵜⰭ䕇✮⦽ ' * 120) + '\\n', encoding='utf-8')",
          "    content_list = run_dir / 'pdf_text_content_list.json'",
          "    content_list.write_text('[]', encoding='utf-8')",
          "    return {",
          "        'source_md_path': str(output_path),",
          "        'content_list_path': str(content_list),",
          "        'content_list_v2_path': None,",
          "        'middle_json_path': None,",
          "        'assets_dir': None,",
          "        'converter': 'pdf_text_layer',",
          "        'warnings': ['fake bad text layer'],",
          "    }",
          "def fake_mineru(**kwargs):",
          "    calls.append(kwargs.get('mode'))",
          "    out = Path(kwargs['output_dir']) / 'mineru_ocr.md'",
          "    out.write_text('# OCR result\\n\\n1. Open settings and keep threshold=0.8.\\n\\nRetry_count=3 must stay.\\n', encoding='utf-8')",
          "    return {",
          "        'source_md_path': str(out),",
          "        'content_list_path': None,",
          "        'content_list_v2_path': None,",
          "        'middle_json_path': None,",
          "        'assets_dir': None,",
          "        'converter': 'mineru',",
          "        'warnings': ['fake mineru fallback'],",
          "    }",
          "pdf_text.convert_text_layer_pdf = bad_text_layer",
          "mineru_adapter.run_mineru = fake_mineru",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({",
          "            'input_path': str(input_path),",
          "            'output_root': str(output_root),",
          "            'profile': 'standard',",
          "            'mode': 'rules_only',",
          "            'language': 'zh',",
          "            'source_type': 'auto',",
          "            'splitter': 'auto',",
          "            'force': True,",
          "        })",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is True, payload",
          "assert calls == ['ocr'], calls",
          "cleaned = Path(payload['data']['latest_outputs']['cleaned_md']).read_text(encoding='utf-8')",
          "report = json.loads(Path(payload['data']['latest_outputs']['conversion_report']).read_text(encoding='utf-8'))",
          "assert 'threshold=0.8' in cleaned, cleaned",
          "assert 'Ჭ䌦圳' not in cleaned, cleaned",
          "assert report['converter'] == 'mineru_after_pdf_text_layer_fallback', report",
          "assert report['mineru_artifacts']['fallback_from'] == 'pdf_text_layer', report",
          "assert any('W_PDF_TEXT_LAYER_FALLBACK_TO_OCR' in warning for warning in report['warnings']), report",
        ].join("\n"),
        [inputPath, outputRoot],
        true,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 10_000);

  it("copies MinerU image assets next to converted Markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-mineru-assets-"));
    try {
      runPython(
        [
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter, prepare",
          "run_dir = Path(__import__('sys').argv[1])",
          "input_path = run_dir / 'sample.pdf'",
          "input_path.write_bytes(b'%PDF-1.4\\n')",
          "def fake_mineru(**kwargs):",
          "    raw = Path(kwargs['output_dir']) / 'mineru_raw' / 'sample' / 'auto'",
          "    images = raw / 'images'",
          "    images.mkdir(parents=True)",
          "    (images / 'kept.jpg').write_bytes(b'jpg')",
          "    source = raw / 'source.md'",
          "    source.write_text('![](images/kept.jpg)\\n', encoding='utf-8')",
          "    return {'source_md_path': str(source), 'converter': 'mineru', 'warnings': []}",
          "mineru_adapter.run_mineru = fake_mineru",
          "converted = run_dir / 'converted.md'",
          "prepare._run_mineru_conversion(input_path, converted, run_dir, 'zh', 'auto')",
          "assert converted.read_text(encoding='utf-8') == '![](images/kept.jpg)\\n'",
          "assert (run_dir / 'images' / 'kept.jpg').read_bytes() == b'jpg'",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("classifies Chinese QR images, proof screenshots, and tutorial screenshots", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-image-classify-"));
    try {
      runPython(
        [
          "from pathlib import Path",
          "from kbprep_worker import images",
          "run_dir = Path(__import__('sys').argv[1])",
          "(run_dir / 'converted.md').write_text('placeholder', encoding='utf-8')",
          "blocks = [",
          "    {",
          "        'block_id': 'qr',",
          "        'type': 'unknown_review',",
          "        'text': '扫码加入社群，免费领取体验卡。\\n![](images/qr.png)',",
          "        'images': [{'src': 'images/qr.png'}],",
          "        'heading_path': [],",
          "        'status': 'unclassified',",
          "    },",
          "    {",
          "        'block_id': 'proof',",
          "        'type': 'unknown_review',",
          "        'text': '这是案例收入数据截图，用来说明变现结果。\\n![](images/proof.png)',",
          "        'images': [{'src': 'images/proof.png'}],",
          "        'heading_path': [],",
          "        'status': 'unclassified',",
          "    },",
          "    {",
          "        'block_id': 'step',",
          "        'type': 'unknown_review',",
          "        'text': '步骤 1：打开后台设置页面，点击保存。\\n![](images/step.png)',",
          "        'images': [{'src': 'images/step.png'}],",
          "        'heading_path': ['实操教程'],",
          "        'status': 'unclassified',",
          "    },",
          "]",
          "classified = {block['block_id']: block for block in images.classify_images(blocks, str(run_dir))}",
          "assert classified['qr']['image_type'] == 'qr_image', classified",
          "assert classified['qr']['status'] == 'discard', classified",
          "assert classified['proof']['image_type'] == 'proof_screenshot', classified",
          "assert classified['proof']['status'] == 'evidence', classified",
          "assert classified['step']['image_type'] == 'operation_screenshot', classified",
          "assert classified['step']['status'] == 'keep', classified",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("copies local Markdown image assets into run and latest outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-md-assets-"));
    try {
      const sourceDir = path.join(root, "source");
      const outputRoot = path.join(root, "out");
      const assetsDir = path.join(sourceDir, "assets");
      const imagesDir = path.join(sourceDir, "images");
      mkdirSync(assetsDir, { recursive: true });
      mkdirSync(imagesDir, { recursive: true });
      const png1x1 = Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
        "base64",
      );
      writeFileSync(path.join(assetsDir, "step.png"), png1x1);
      writeFileSync(path.join(assetsDir, "chart.png"), png1x1);
      writeFileSync(path.join(imagesDir, "result.png"), png1x1);

      const inputPath = path.join(sourceDir, "note.md");
      writeFileSync(
        inputPath,
        [
          "# 操作截图",
          "",
          "步骤 1：打开后台，把 threshold=0.8 填到配置项。",
          "![步骤截图](assets/step.png)",
          "",
          "步骤 2：检查结果图，确认参数没有丢。",
          "![[assets/chart.png]]",
          "",
          "![结果图](images/result.png)",
        ].join("\n"),
        "utf8",
      );

      const result = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        source_type: "auto",
        splitter: "auto",
        force: true,
      });

      expect(result.ok).toBe(true);
      const latest = result.data.latest_outputs;
      const converted = readFileSync(latest.converted_md, "utf8");
      const cleaned = readFileSync(latest.cleaned_md, "utf8");
      const report = JSON.parse(readFileSync(latest.quality_report, "utf8"));

      expect(converted).toContain("![步骤截图](images/assets/step.png)");
      expect(converted).toContain("![](images/assets/chart.png)");
      expect(converted).toContain("![结果图](images/result.png)");
      expect(converted).not.toContain("images/images/result.png");
      expect(cleaned).toContain("threshold=0.8");
      expect(existsSync(path.join(result.data.run_dir, "images", "assets", "step.png"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "images", "assets", "step.png"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "images", "assets", "chart.png"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "images", "result.png"))).toBe(true);
      expect(report.image_retention.missing_file_count).toBe(0);
      expect(report.strict_errors).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails prepare when strict quality gates fail instead of publishing latest outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-strict-gate-"));
    try {
      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import prepare, quality",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "input_path.write_text('# Clean text\\n\\nStep 1: keep threshold=0.8.\\n', encoding='utf-8')",
          "def fake_quality(**kwargs):",
          "    return {'strict_errors': ['E_QA_FAILED: forced strict error'], 'warnings': []}",
          "quality.run_quality_check = fake_quality",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'lite', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True})",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is False, payload",
          "assert payload['error']['code'] == 'E_QA_FAILED', payload",
          "assert 'run_dir' in payload['error']['details'], payload",
          "assert not (output_root / 'latest.json').exists(), list(output_root.iterdir())",
        ].join("\n"),
        [path.join(root, "input.md"), path.join(root, "output")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("unwraps trusted PDF text-layer hard line breaks without merging structural lines", () => {
    runPython(
      [
        "from kbprep_worker.pdf_text import _normalize_page_text",
        "raw = '\\n'.join([",
        "    '2026AI+美妆消费趋势报告',",
        "    '科技赋能，精准定义新美学生态',",
        "    '',",
        "    'AI技术从产品研',",
        "    '发、消费者体验与品牌沟通模式重塑行业。',",
        "    '- 保留列表项一',",
        "    '- 保留列表项二',",
        "    '<!-- page: 2 -->',",
        "    '新的页面标记不能合并'",
        "])",
        "normalized = _normalize_page_text(raw)",
        "assert 'AI技术从产品研发、消费者体验与品牌沟通模式重塑行业。' in normalized, normalized",
        "assert '产品研\\n发、消费者' not in normalized, normalized",
        "assert '2026AI+美妆消费趋势报告\\n科技赋能，精准定义新美学生态' in normalized, normalized",
        "assert '- 保留列表项一\\n- 保留列表项二' in normalized, normalized",
        "assert '<!-- page: 2 -->\\n新的页面标记不能合并' in normalized, normalized",
      ].join("\n"),
      [],
    );
  });

  it("rejects AI review patches that rewrite text, drop protected blocks, or use invalid metadata", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "review-safety.md");
      writeFileSync(
        sourcePath,
        [
          "# Review Safety",
          "",
          "第一步：保留 REVIEW_STEP_MARKER，把参数 threshold 设置为 0.8，并记录失败原因。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_plus_review_pack",
        language: "zh",
        force: true,
      });

      const blocks = readFileSync(path.join(prepared.data.run_dir, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const stepBlock = blocks.find((block) => block.type === "operation_step");
      const ctaBlock = blocks.find((block) => block.type === "marketing_cta");
      expect(stepBlock).toBeDefined();
      expect(ctaBlock).toBeDefined();

      const patched = runWorker("apply_review", {
        run_dir: prepared.data.run_dir,
        patch_json: [
          { op: "replace", path: `/blocks/${stepBlock.block_id}/text`, value: "总结成一句话" },
          { op: "replace", path: `/blocks/${stepBlock.block_id}/status`, value: "discard" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/status`, value: "gone" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/status/extra`, value: "evidence" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/risk_tags`, value: "not-array" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/confidence`, value: "high" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/status`, value: "review" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/reason`, value: "needs human review" },
        ],
      });

      const cleaned = readFileSync(path.join(prepared.data.run_dir, "cleaned.md"), "utf8");
      const reviewNeeded = readFileSync(path.join(prepared.data.run_dir, "review_needed.md"), "utf8");
      const topLevelReviewNeeded = readFileSync(path.join(outputRoot, "review_needed.md"), "utf8");
      const latest = JSON.parse(readFileSync(path.join(outputRoot, "latest.json"), "utf8"));
      const updatedQuality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const updatedBlocks = readFileSync(path.join(prepared.data.run_dir, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const updatedStep = updatedBlocks.find((block) => block.block_id === stepBlock.block_id);
      const updatedCta = updatedBlocks.find((block) => block.block_id === ctaBlock.block_id);

      expect(patched.data.applied).toBe(2);
      expect(patched.data.rejected).toBe(6);
      expect(patched.data.published).toBe(true);
      expect(updatedStep.text).toContain("REVIEW_STEP_MARKER");
      expect(updatedStep.status).toBe("keep");
      expect(updatedCta.status).toBe("review");
      expect(Array.isArray(updatedCta.risk_tags)).toBe(true);
      expect(typeof updatedCta.confidence).toBe("number");
      expect(cleaned).toContain("REVIEW_STEP_MARKER");
      expect(topLevelReviewNeeded).toContain("needs human review");
      expect(latest.review_applied_at).toBeTypeOf("number");
      expect(updatedQuality.runtime_cache_key).toBeTypeOf("string");
      expect(updatedQuality.runtime.python_executable).toContain("python");
      expect(updatedQuality.plugin_version).toBe(JSON.parse(readFileSync("package.json", "utf8")).version);
      expect(updatedQuality.review_applied_at).toBeTypeOf("number");
      expect(reviewNeeded).toContain("扫码加入社群领取体验卡");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects review patches that discard unprotected detail-bearing paragraphs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-review-detail-"));
    try {
      runPython(
        [
          "import json, sys",
          "from pathlib import Path",
          "from kbprep_worker.apply_patch import run",
          "run_dir = Path(sys.argv[1])",
          "run_dir.mkdir(parents=True, exist_ok=True)",
          "(run_dir / 'chunks').mkdir()",
          "(run_dir / 'diagnosis_report.json').write_text(json.dumps({'diagnosis': {'file_id': 'review-detail'}}), encoding='utf-8')",
          "(run_dir / 'quality_report.json').write_text(json.dumps({'source_type': 'markdown_note', 'source_sha256': 'review-detail', 'plugin_version': '0.4.1'}), encoding='utf-8')",
          "blocks = [",
          "  {'block_id': 'detail1', 'source_sha256': 'review-detail', 'status': 'keep', 'type': 'paragraph', 'text': '失败经验：连续 3 次失败时，记录 failure_reason 并人工复查。', 'protected': False, 'risk_tags': [], 'confidence': 0.7},",
          "  {'block_id': 'cta1', 'source_sha256': 'review-detail', 'status': 'discard', 'type': 'marketing_cta', 'text': '扫码入群领取体验卡', 'protected': False, 'risk_tags': [], 'confidence': 0.95},",
          "]",
          "(run_dir / 'blocks.jsonl').write_text('\\n'.join(json.dumps(b, ensure_ascii=False) for b in blocks) + '\\n', encoding='utf-8')",
          "run({'run_dir': str(run_dir), 'patch_json': [",
          "  {'op': 'replace', 'path': '/blocks/detail1/status', 'value': 'discard'},",
          "  {'op': 'replace', 'path': '/blocks/cta1/status', 'value': 'review'},",
          "]})",
        ].join("\n"),
        [root],
      );

      const blocks = readFileSync(path.join(root, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const detailBlock = blocks.find((block) => block.block_id === "detail1");
      const ctaBlock = blocks.find((block) => block.block_id === "cta1");
      const quality = JSON.parse(readFileSync(path.join(root, "quality_report.json"), "utf8"));

      expect(detailBlock.status).toBe("keep");
      expect(ctaBlock.status).toBe("review");
      expect(quality.detail_retention.discarded_detail_block_ids).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails invalid PPTX inputs before publishing cleaned outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "broken.pptx");
      writeFileSync(sourcePath, "this is not a valid office zip container", "utf8");

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      }, 1);

      const originalsDir = path.join(outputRoot, "original");
      const originalBackups = existsSync(originalsDir)
        ? readdirSync(originalsDir).filter((name) => name.endsWith(".pptx"))
        : [];

      expect(envelope.ok).toBe(false);
      expect(envelope.error.code).toBe("E_CONVERT_INPUT_INVALID");
      expect(envelope.error.message).toContain("not a valid Office ZIP container");
      expect(envelope.error.details.run_dir).toContain("runs");
      expect(envelope.error.details.original_file).toContain(".pptx");
      expect(existsSync(envelope.error.details.error_report)).toBe(true);
      const errorReport = JSON.parse(readFileSync(envelope.error.details.error_report, "utf8"));
      expect(errorReport.code).toBe("E_CONVERT_INPUT_INVALID");
      expect(errorReport.original_file).toContain(".pptx");
      expect(errorReport.runtime.python_executable).toContain("python");
      expect(originalBackups.length).toBe(1);
      expect(existsSync(path.join(outputRoot, "cleaned.md"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "latest.json"))).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects audio/video binaries instead of pretending to transcribe them", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.mp4");
      writeFileSync(sourcePath, "not a real video", "utf8");

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      }, 1);

      expect(envelope.ok).toBe(false);
      expect(envelope.error.code).toBe("E_UNSUPPORTED_TYPE");
      expect(envelope.error.message).toContain("not transcribed in v1");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("writes separate direct-use outputs for each file in a batch", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      writeFileSync(
        path.join(inputDir, "alpha.md"),
        [
          "# Alpha 教程",
          "",
          "第一步：保留 ALPHA_UNIQUE_MARKER，并记录参数 threshold=0.8。",
          "",
          "第二步：保留失败经验和限制条件，方便后续复盘。",
        ].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "beta.md"),
        [
          "# Beta 教程",
          "",
          "第一步：保留 BETA_UNIQUE_MARKER，并记录参数 retry_count=3。",
          "",
          "第二步：保留操作步骤和判断标准，不能总结成一句话。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare_batch", {
        input_dir: inputDir,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
        convert_jobs: 1,
      });

      const results = envelope.data.results as Array<{
        file: string;
        latest_outputs: { cleaned_md: string };
      }>;
      const cleanedDirs = new Set(results.map((result) => path.dirname(result.latest_outputs.cleaned_md)));

      expect(envelope.data.failed).toBe(0);
      expect(results).toHaveLength(2);
      expect(cleanedDirs.size).toBe(2);

      const alpha = results.find((result) => result.file === "alpha.md");
      const beta = results.find((result) => result.file === "beta.md");
      expect(alpha).toBeDefined();
      expect(beta).toBeDefined();

      const alphaCleaned = readFileSync(alpha!.latest_outputs.cleaned_md, "utf8");
      const betaCleaned = readFileSync(beta!.latest_outputs.cleaned_md, "utf8");
      expect(alphaCleaned).toContain("ALPHA_UNIQUE_MARKER");
      expect(alphaCleaned).not.toContain("BETA_UNIQUE_MARKER");
      expect(betaCleaned).toContain("BETA_UNIQUE_MARKER");
      expect(betaCleaned).not.toContain("ALPHA_UNIQUE_MARKER");
      expect(existsSync(path.join(outputRoot, "progress.json"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "failures.json"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("writes a batch inventory for unsupported local files instead of silently ignoring them", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-batch-inventory-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      writeFileSync(
        path.join(inputDir, "alpha.md"),
        ["# Alpha", "", "步骤1：保留 ALPHA_BATCH_MARKER，设置 threshold=0.8。"].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "repo.py"),
        ["retry_count = 3", "failure_reason = 'timeout'"].join("\n"),
        "utf8",
      );
      writeFileSync(path.join(inputDir, "lesson.mp4"), "not a real video", "utf8");
      writeFileSync(path.join(inputDir, "archive.bin"), "unknown local file", "utf8");

      const envelope = runWorker("prepare_batch", {
        input_dir: inputDir,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
        convert_jobs: 1,
      });

      const inventoryPath = envelope.data.batch_inventory_json;
      const inventory = JSON.parse(readFileSync(inventoryPath, "utf8")) as {
        files: Array<{ file: string; action: string; reason?: string; detected_format?: string }>;
      };

      expect(envelope.data.total).toBe(2);
      expect(envelope.data.discovered_total).toBe(4);
      expect(envelope.data.skipped_unsupported).toBe(2);
      expect(envelope.data.failed).toBe(0);
      expect(inventory.files.find((item) => item.file === "alpha.md")?.action).toBe("process");
      expect(inventory.files.find((item) => item.file === "repo.py")?.detected_format).toBe("code");
      expect(inventory.files.find((item) => item.file === "lesson.mp4")?.reason).toContain("media_binary_not_transcribed");
      expect(inventory.files.find((item) => item.file === "archive.bin")?.reason).toContain("unsupported_extension");
      expect(envelope.data.results.map((result: { file: string }) => result.file).sort()).toEqual(["alpha.md", "repo.py"]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("recursively processes useful nested source files while skipping noisy project directories", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-recursive-batch-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(path.join(inputDir, "docs"), { recursive: true });
      mkdirSync(path.join(inputDir, "examples"), { recursive: true });
      mkdirSync(path.join(inputDir, "node_modules", "noise"), { recursive: true });
      mkdirSync(outputRoot);
      writeFileSync(
        path.join(inputDir, "docs", "guide.md"),
        ["# GitHub Guide", "", "步骤1：保留 GITHUB_DOC_MARKER，并设置 threshold=0.8。"].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "examples", "script.py"),
        ["retry_count = 3", "failure_reason = 'timeout'"].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "node_modules", "noise", "ad.md"),
        "# Dependency noise\n\nSHOULD_NOT_BE_PROCESSED",
        "utf8",
      );

      const envelope = runWorker("prepare_batch", {
        input_dir: inputDir,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
        convert_jobs: 1,
      });

      const inventory = JSON.parse(readFileSync(envelope.data.batch_inventory_json, "utf8")) as {
        discovered_total: number;
        files: Array<{ file: string; relative_path: string; action: string; detected_format?: string }>;
      };
      const results = envelope.data.results as Array<{
        file: string;
        relative_path: string;
        latest_outputs: { cleaned_md: string };
      }>;

      expect(envelope.data.failed).toBe(0);
      expect(envelope.data.total).toBe(2);
      expect(inventory.discovered_total).toBe(2);
      expect(inventory.files.map((item) => item.relative_path).sort()).toEqual([
        "docs/guide.md",
        "examples/script.py",
      ]);
      expect(results.map((item) => item.relative_path).sort()).toEqual([
        "docs/guide.md",
        "examples/script.py",
      ]);
      expect(readFileSync(results.find((item) => item.relative_path === "docs/guide.md")!.latest_outputs.cleaned_md, "utf8"))
        .toContain("GITHUB_DOC_MARKER");
      expect(results.some((item) => item.relative_path.includes("node_modules"))).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("runs heavy batch conversion files serially even when convert_jobs is greater than one", () => {
    runPython(
      [
        "import io, json, sys, tempfile, threading, time",
        "from pathlib import Path",
        "from kbprep_worker import prepare_batch",
        "root = Path(tempfile.mkdtemp(prefix='kbprep-heavy-batch-'))",
        "input_dir = root / 'input'",
        "output_root = root / 'output'",
        "input_dir.mkdir()",
        "output_root.mkdir()",
        "(input_dir / '00-sample.md').write_text('# Sample\\n\\n步骤1：保留样本。', encoding='utf-8')",
        "(input_dir / '01-heavy.pdf').write_bytes(b'%PDF-1.4 heavy one')",
        "(input_dir / '02-heavy.pdf').write_bytes(b'%PDF-1.4 heavy two')",
        "(input_dir / '03-note.md').write_text('# Note\\n\\n步骤1：轻文本。', encoding='utf-8')",
        "lock = threading.Lock()",
        "active_pdf = 0",
        "max_active_pdf = 0",
        "calls = []",
        "def fake_process_one_file(file_path, output_root, profile, language, mode, force):",
        "    global active_pdf, max_active_pdf",
        "    suffix = Path(file_path).suffix.lower()",
        "    calls.append(Path(file_path).name)",
        "    if suffix == '.pdf':",
        "        with lock:",
        "            active_pdf += 1",
        "            max_active_pdf = max(max_active_pdf, active_pdf)",
        "        time.sleep(0.08)",
        "        with lock:",
        "            active_pdf -= 1",
        "    return {'ok': True, 'data': {'run_id': Path(file_path).stem, 'strict_errors': [], 'latest_outputs': {'cleaned_md': str(Path(output_root) / 'cleaned.md')}}}",
        "prepare_batch._process_one_file = fake_process_one_file",
        "stdout = io.StringIO()",
        "old_stdout = sys.stdout",
        "try:",
        "    sys.stdout = stdout",
        "    try:",
        "        prepare_batch.run({",
        "            'input_dir': str(input_dir),",
        "            'output_root': str(output_root),",
        "            'profile': 'standard',",
        "            'mode': 'rules_only',",
        "            'language': 'zh',",
        "            'force': True,",
        "            'convert_jobs': 3,",
        "        })",
        "    except SystemExit:",
        "        pass",
        "finally:",
        "    sys.stdout = old_stdout",
        "payload = json.loads(stdout.getvalue())",
        "assert payload['ok'] is True, payload",
        "assert max_active_pdf == 1, {'max_active_pdf': max_active_pdf, 'calls': calls}",
        "assert payload['data']['heavy_conversion_files'] == 2, payload",
        "assert payload['data']['heavy_conversion_concurrency'] == 1, payload",
      ].join("\n"),
      [],
    );
  });

  it("renders long documents into ordered parts that reconstruct cleaned markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "long-guide.md");
      const chapters = Array.from({ length: 9 }, (_, index) => {
        const chapterNo = index + 1;
        const body = Array.from({ length: 18 }, (__, paragraphIndex) =>
          `第${chapterNo}章第${paragraphIndex + 1}段：这是一个教程正文段落，保留 LONG_PART_MARKER_${chapterNo}_${paragraphIndex + 1}。这里包含工具名 OpenClaw、参数 threshold=0.8、retry_count=3、失败原因、限制条件和复盘标准，不能被总结成概念。`,
        ).join("\n\n");
        return `# 第${chapterNo}章 长文档章节 ${chapterNo}\n\n${body}`;
      }).join("\n\n");
      writeFileSync(sourcePath, chapters, "utf8");

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const cleaned = normalizeMarkdownText(readFileSync(path.join(outputRoot, "cleaned.md"), "utf8"));
      const partsDir = path.join(outputRoot, "parts");
      const manifestPath = path.join(partsDir, "parts_manifest.json");
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Array<{
        part_id: string;
        block_ids: string[];
        char_count: number;
      }>;
      const partFiles = readdirSync(partsDir).filter((name) => /^part_\d{3}\.md$/.test(name)).sort();
      const reconstructed = partFiles.map((name) => {
        const raw = readFileSync(path.join(partsDir, name), "utf8");
        return normalizeMarkdownText(raw.replace(/^---[\s\S]*?---\s*/, ""));
      }).join("\n\n").trim();

      expect(envelope.data.strict_errors).toEqual([]);
      expect(partFiles.length).toBeGreaterThan(1);
      expect(manifest.map((entry) => `${entry.part_id}.md`)).toEqual(partFiles);
      expect(manifest.every((entry) => entry.block_ids.length > 0 && entry.char_count > 0)).toBe(true);
      expect(reconstructed).toBe(cleaned);
      expect(cleaned.indexOf("LONG_PART_MARKER_1_1")).toBeLessThan(cleaned.indexOf("LONG_PART_MARKER_9_18"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("diagnoses text-layer, image-only, and PPT-like PDFs differently", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const outputRoot = path.join(root, "output");
      mkdirSync(outputRoot);
      const textPdf = path.join(root, "text-layer.pdf");
      const imagePdf = path.join(root, "image-only.pdf");
      const imagePath = path.join(root, "pixel.png");
      const slidePdf = path.join(root, "slide-export.pdf");
      const slideImagePath = path.join(root, "slide-pixel.png");
      const slideTextPdf = path.join(root, "slide-text-layer.pdf");
      const garbledPdf = path.join(root, "garbled-text-layer.pdf");

      makeTextLayerPdf(textPdf);
      makeImageOnlyPdf(imagePdf, imagePath);
      makeLandscapeImagePdf(slidePdf, slideImagePath);
      makeLandscapeTextPdf(slideTextPdf);
      makeGarbledTextLayerPdf(garbledPdf);

      const textDiag = runWorker("diagnose", {
        input_path: textPdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const imageDiag = runWorker("diagnose", {
        input_path: imagePdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const slideDiag = runWorker("diagnose", {
        input_path: slidePdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const slideTextDiag = runWorker("diagnose", {
        input_path: slideTextPdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const garbledDiag = runWorker("diagnose", {
        input_path: garbledPdf,
        output_root: outputRoot,
        source_type: "auto",
      });

      expect(textDiag.data.detected_format).toBe("pdf");
      expect(textDiag.data.source_type).toBe("pdf_like");
      expect(textDiag.data.pdf_subtype).toBe("text_layer");
      expect(textDiag.data.needs_ocr).toBe(false);
      expect(textDiag.data.text_pages).toBe(1);
      expect(textDiag.data.text_profile).toBe("tutorial");
      expect(textDiag.data.char_count).toBeGreaterThan(20);
      expect(textDiag.data.recommended_pipeline).toBe("pdf_text_layer");
      expect(textDiag.data.conversion_strategy).toBe("pdf_text_layer");
      expect(textDiag.data.split_strategy).toBe("content_structure");

      expect(imageDiag.data.detected_format).toBe("pdf");
      expect(imageDiag.data.source_type).toBe("pdf_like");
      expect(imageDiag.data.pdf_subtype).toBe("image_only_or_scanned");
      expect(imageDiag.data.needs_ocr).toBe(true);
      expect(imageDiag.data.image_pages).toBe(1);
      expect(imageDiag.data.text_pages).toBe(0);
      expect(imageDiag.data.conversion_strategy).toBe("mineru_ocr");

      expect(slideDiag.data.detected_format).toBe("pdf");
      expect(slideDiag.data.pdf_subtype).toBe("ppt_exported_or_scanned");
      expect(slideDiag.data.needs_ocr).toBe(true);
      expect(slideDiag.data.landscape_pages).toBe(3);
      expect(slideDiag.data.layout_profile).toBe("slide_deck_or_ppt_export");
      expect(slideDiag.data.conversion_strategy).toBe("mineru_ocr");
      expect(slideDiag.data.split_strategy).toBe("preserve_slide_or_page_order");

      expect(slideTextDiag.data.pdf_subtype).toBe("ppt_exported_text_layer");
      expect(slideTextDiag.data.needs_ocr).toBe(false);
      expect(slideTextDiag.data.layout_profile).toBe("slide_deck_or_ppt_export");
      expect(slideTextDiag.data.slide_like_score).toBeGreaterThanOrEqual(0.65);
      expect(slideTextDiag.data.average_text_chars_per_text_page).toBeGreaterThan(20);
      expect(slideTextDiag.data.recommended_pipeline).toBe("pdf_text_layer");
      expect(slideTextDiag.data.conversion_strategy).toBe("pdf_text_layer_slide_order");
      expect(slideTextDiag.data.split_strategy).toBe("preserve_slide_or_page_order");
      expect(JSON.stringify(slideTextDiag.data.processing_hints)).toContain("preserve slide/page order");

      expect(garbledDiag.data.pdf_subtype).toBe("garbled_text_layer");
      expect(garbledDiag.data.text_layer_health).toBe("bad");
      expect(garbledDiag.data.needs_ocr).toBe(true);
      expect(garbledDiag.data.conversion_strategy).toBe("mineru_ocr");
      expect(garbledDiag.data.text_quality.unreadable_text_ratio).toBeGreaterThan(0.3);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
