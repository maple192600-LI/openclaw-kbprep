# KBPrep 项目现状与开发实施文档

更新时间：2026-06-10

## 1. 文档定位

本文是 KBPrep 当前开发实施文档，用于把“最高设计目标”和“现有代码状态”对齐，并给出下一阶段可执行路线。

最高开发参考文件：

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`

这两个文件只作为本实施文档的依据，不在本文任务中修改。

当前项目阶段判断：**自用工具阶段，正在向正式项目能力靠拢**。

原因：项目已经有 CLI、Python worker、质量报告、批处理、反馈提案、清理生命周期和测试，但主要使用场景仍是本地资料处理，不应直接扩展成 SaaS、云服务、多租户或复杂权限系统。

## 2. 当前项目一句话状态

KBPrep 当前已经具备“本地文件转 Markdown 或 Obsidian 输出”的主流程基础，但距离最高设计文档要求的完整质量流水线还有差距。

当前更准确的状态是：

> 已经有单文件和批量处理骨架、部分转换路线、规则清洗、质量门和反馈提案；下一阶段重点不是堆新功能，而是把“转换质量先验、分块级验收、失败定位、受影响部分复跑、工具路线可替换”做扎实。

## 3. 现有能力盘点

### 3.1 应保留的能力

这些是项目已经形成价值的底座，应继续保留：

| 能力 | 当前位置 | 保留原因 |
| --- | --- | --- |
| Host-neutral CLI | `src/adapters/standalone/` | 不绑定 Claude Code、Codex、OpenClaw，符合项目边界。 |
| Python worker 主流程 | `python/kbprep_worker/stages/pipeline_core.py` | 已有清晰阶段：诊断、转换、归一化、分块、分类、清洗、质量检查、发布。 |
| 能力矩阵 | `python/kbprep_worker/converter_capabilities.py`、`docs/capability-matrix.md` | 已经能区分 verified、partial、unsupported，避免假装全支持。 |
| 质量报告 | `python/kbprep_worker/quality/` | 已有转换完整性、清洗安全、分块完整性、导出阻断等检查。 |
| 失败不发布 | `pipeline_core._stage_publish_or_block` | 严格错误存在时不更新 `latest.json`，符合“不过关不能发布”。 |
| 规则字典 | `rules/` | 清洗知识放规则，不硬编码平台、作者、课程品牌，符合边界。 |
| 反馈提案机制 | `python/kbprep_worker/feedback/` | 用户反馈先进入 proposal，不能直接变长期规则。 |
| 批处理 sample-first | `python/kbprep_worker/prepare_batch.py` | 批量前先跑样本，能降低大批量误处理风险。 |
| 清理生命周期 | `python/kbprep_worker/cleanup.py` | 区分最终交付物和临时过程材料，降低误删风险。 |
| 打包检查 | `scripts/check-pack.mjs` | 能防止发布包缺关键文件。 |

### 3.2 已验证或基本可用的输入类型

| 输入类型 | 当前状态 | 说明 |
| --- | --- | --- |
| Markdown、TXT、CSV、TSV | verified | 直接读取，已有基础结构保留测试。 |
| JSON | verified | 能转成可读 Markdown，但大型机器 JSON 仍需知识化规则。 |
| 代码和配置文件 | verified | 会保护代码、参数、URL，不应被普通正文清洗误伤。 |
| 字幕文件 | verified | 可保留时间轴和顺序，适合作为音视频的第一阶段替代输入。 |

### 3.3 部分可用但需要迭代的输入类型

| 输入类型 | 当前状态 | 当前风险 |
| --- | --- | --- |
| HTML | partial | 能提取可读内容，但网页导航、页脚、广告、cookie 等噪音处理证据不足。 |
| DOCX、PPTX、XLSX | partial | 本地 Office XML 路线能用，但复杂表格、图表、幻灯片语义证据不足。 |
| EPUB | partial | 能按 XHTML 抽取，但脚注、复杂表格、图片和章节顺序需要更多样本。 |
| PDF | partial | 已有 PyMuPDF 文本层和 MinerU/OCR 路线，但复杂排版、表格、图片和坏文本层需要更多黄金样本。 |

### 3.4 当前不应宣称支持的输入类型

| 输入类型 | 当前状态 | 处理原则 |
| --- | --- | --- |
| 图片文件独立 OCR | unsupported | 不能假装成功。需要先接入现成 OCR 工具并做样本验证。 |
| 旧 Office：DOC、PPT、XLS | unsupported | 应提示用户先转成 DOCX、PPTX、XLSX、PDF 或 Markdown。 |
| MOBI | unsupported | 应用外部电子书工具先转 EPUB 或 Markdown。 |
| 音频、视频二进制 | unsupported | 当前应要求用户提供字幕或转写文本；后续可引入 ASR。 |
| 平台链接 | not implemented | 需要先设计下载、版权、登录和失败提示边界。 |

## 4. 对照最高流程的差距

| 最高流程阶段 | 当前状态 | 结论 |
| --- | --- | --- |
| 用户给资料、入口接收 | 基本存在 | CLI 输入和批量目录扫描已有，但 URL、平台链接、音视频入口未完整。 |
| 识别来源和格式 | 部分存在 | 本地文件扩展名、PDF/Office 基础诊断已有；来源级身份和网页来源还弱。 |
| 选择转换路线 | 部分存在 | 有能力矩阵和 route decision，但还缺多工具候选比较机制。 |
| 转成基础 Markdown | 部分存在 | 直接文本、Office XML、EPUB、PDF/MinerU 已有，但复杂格式证据不足。 |
| 转换质量检测 | 已有基础 | 已检查乱码、结构丢失、图片引用等；需要按工具路线扩充黄金样本。 |
| 大小判断和自然分块 | 部分存在 | 有 split/chunks，但还没完全达到“按章节、页码、表格、代码、步骤不可切碎”的目标。 |
| 资料类型判断 | 部分存在 | 有 document_type，但规则覆盖和证据仍需扩充。 |
| 选择清洗规则和保护规则 | 已有基础 | 规则字典和保护块存在，但来源专属规则、反例验证需加强。 |
| 逐块清洗、逐块验收 | 部分存在 | 有 block 级状态和质量报告，但失败后自动定位到具体块和复跑范围还不够。 |
| 失败定位、修复任务、规则提案 | 部分存在 | `quality_tasks` 已有雏形；需要更具体地绑定失败块、工具路线和复跑命令。 |
| 复跑受影响分块 | 薄弱 | 反馈接受后可复跑来源，但“只复跑受影响分块”还不是主流程能力。 |
| 合并前整体检查 | 部分存在 | 有最终质量检查和输出阻断，但章节连续、上下文衔接的证据还弱。 |
| 输出交付物 | 已有基础 | standard Markdown 和 Obsidian 目录都存在，且区分最终/过程材料。 |
| 用户复查和反馈进规则库 | 已有基础 | feedback proposal、accept/reject、rerun verification 已有；还需更易用的操作文档和界面提示。 |

## 5. 下一阶段保留、迭代、更新清单

### 5.1 必须保留

1. 保留 host-neutral 边界，不做任何主机专属业务逻辑。
2. 保留 `latest.json` 只在质量通过后更新的规则。
3. 保留 `converted.md`、`blocks.jsonl`、`discarded.md`、`review_needed.md`、`quality_report.json` 这些审计材料。
4. 保留规则字典优先，不把平台、作者、课程品牌写死进 Python。
5. 保留反馈先提案、再验证、再接受的规则库流程。

### 5.2 优先迭代

1. 转换路线注册表：把 MinerU、Docling、Pandoc、Trafilatura、ASR 等都接成可评估的 route，而不是散落在代码里。
2. 黄金样本库：为 PDF、Office、HTML、EPUB、图片、字幕建立最小真实样本集。
3. 转换对比报告：同一文件可用不同工具转换，自动比较标题、表格、图片、代码、顺序、字数、乱码率。
4. 分块验收：把失败定位从“整份文件失败”推进到“哪个块、什么原因、该改规则还是改转换”。
5. 受影响复跑：规则或转换修复后，只复跑相关来源或相关分块，并再次进入质量门。
6. 用户可读错误：每个失败必须给出“你该看哪个文件、发哪段错误、下一步怎么做”。

### 5.3 需要更新

1. 更新 `docs/capability-matrix.md`：增加外部候选工具路线和评估状态。
2. 更新 `docs/known-issues.md`：把图片 OCR、旧 Office/MOBI、音视频、网页链接列为明确路线而非模糊 backlog。
3. 更新 `skills/kbprep/SKILL.md`：让使用者知道哪些输入可直接跑，哪些必须先预处理。
4. 更新测试策略：从“功能跑通”升级到“源文件证据是否被保留”。
5. 更新安装说明：未来新增大依赖时必须分 optional extra，不能让轻量用户默认装重模型。

## 6. GitHub 工具调查方法

调查时间：2026-06-10。

使用方法：

- GitHub CLI / REST API 查询仓库活跃度、星标、fork、最近 push、最新 release、许可证。
- GitHub README 和官方文档确认功能范围。
- 只把外部工具作为候选转换路线，不让它们绕过 KBPrep 的质量门。

评价维度：

1. 是否仍在维护：最近 push、最近 release。
2. 是否适合本地运行。
3. 是否能输出 Markdown、JSON 或结构化中间结果。
4. 是否保留标题、表格、图片、代码、页序、时间轴等证据。
5. 许可证是否适合本地工具集成。
6. 依赖是否过重，是否应作为 optional extra。

## 7. 候选工具调查结论

### 7.1 文档解析、PDF、OCR、Office

| 工具 | GitHub 状态 | 适合用途 | 结论 |
| --- | --- | --- | --- |
| MinerU | 67.1k stars；2026-06-10 有 push；2026-06-04 release；支持 PDF、图片、DOCX、PPTX、XLSX 到 Markdown/JSON | 当前 PDF/OCR 主路线，复杂文档解析 | **保留为主路线**。已经在项目中使用，继续强化质量证据。注意许可证是自定义开源许可，不能只按 Apache/MIT 处理。 |
| Docling | 61.3k stars；2026-06-10 有 push；2026-06-09 release；MIT | PDF、Office、HTML、EPUB、图片、ASR 等多格式解析 | **作为第一优先新增候选路线**。先做对比实验，不立刻替换 MinerU。 |
| MarkItDown | 150k stars；2026-05-26 release；MIT | 轻量文件到 Markdown | **适合作轻量 fallback 或对照组**。不适合作唯一主路线，因为目标是质量闭环，不只是快速转 Markdown。 |
| Unstructured | 14.9k stars；2026-06-09 push；2026-06-08 release；Apache-2.0 | 文档 ETL、分区、结构化 | **暂不优先接入主流程**。能力强但偏 ETL 平台，依赖和产品边界更重，可作为后续对比。 |
| PaddleOCR | 81.7k stars；2026-06-10 push；2026-05-28 release；Apache-2.0 | 独立图片 OCR、结构识别 | **作为图片 OCR 候选**。只有当 KBPrep 要直接支持图片输入时再接入；否则优先通过 MinerU/Docling 路线覆盖。 |

参考：MinerU README 说明其支持 PDF、图片、DOCX、PPTX、XLSX 到 Markdown/JSON，并支持扫描件、表格、公式、109 语言 OCR；Docling README 说明其可导出 Markdown、HTML、WebVTT、lossless JSON，并支持 OCR、图片、ASR、本地运行；MarkItDown README 明确定位为轻量 Python Markdown 转换工具。

### 7.2 HTML 和网页正文提取

| 工具 | GitHub 状态 | 适合用途 | 结论 |
| --- | --- | --- | --- |
| Trafilatura | 6.1k stars；2026-06-07 release；Apache-2.0 | 网页正文、元数据、HTML 到 MD/TXT/JSON/XML | **优先接入 HTML/URL 正文提取路线**。比手写 BeautifulSoup 规则更适合真实网页。 |
| Mozilla Readability | 11.3k stars；2026-01-21 push | 文章正文提取 | **可作为 Node 侧备选**。但 KBPrep 主 worker 在 Python，优先 Trafilatura 更顺。 |

### 7.3 Office、电子书、标记格式转换

| 工具 | GitHub 状态 | 适合用途 | 结论 |
| --- | --- | --- | --- |
| Pandoc | 44.7k stars；2026-06-09 push；2026-06-04 release；GPL-2.0 | DOCX、EPUB、HTML、Markdown 等格式互转 | **适合作外部预转换工具或可选路线**。许可证和二进制依赖需要隔离，不建议直接作为内置默认依赖。 |
| Mammoth.js | 6.2k stars；2026-05-24 push；BSD-2-Clause | DOCX 到语义 HTML | **可作为 DOCX 专项备选**。如果 Docling/MinerU 对某些 DOCX 样本失败，再考虑。 |
| Calibre | 25k stars；2026-06-10 push；2026-05-28 release；GPL-3.0 | MOBI/EPUB 等电子书格式转换 | **适合用户侧预处理**。不建议直接嵌入核心依赖，避免安装和许可证复杂度。 |
| EbookLib | 1.8k stars；2025-11-18 push；AGPL-3.0 | EPUB 读写 | **不建议优先接入**。项目现有 EPUB XHTML 路线更轻，且 AGPL 会增加合规风险。 |

### 7.4 音视频、字幕、平台链接

| 工具 | GitHub 状态 | 适合用途 | 结论 |
| --- | --- | --- | --- |
| yt-dlp | 169.6k stars；2026-06-09 release；Unlicense | 下载平台字幕、音视频元数据 | **只建议用于字幕/元数据获取，不建议默认下载视频本体**。需要清楚提示版权、登录和网站限制。 |
| faster-whisper | 23.5k stars；2025-11-19 push；2025-10-31 release；MIT | Python 本地 ASR 转写 | **音频转写第一候选**。如果要做音视频输入，先做 optional extra 和小样本验证。 |
| whisper.cpp | 50.6k stars；2026-06-09 push；2026-06-02 release；MIT | 本地离线 ASR，独立二进制 | **适合作低依赖本地二进制路线**。Windows 打包和模型管理需要单独设计。 |

## 8. 推荐工具路线

### 8.1 第一批推荐接入

1. **Trafilatura**
   - 解决 HTML/URL 正文提取弱的问题。
   - 依赖相对可控，Python worker 直接可用。
   - 输出仍必须进入 KBPrep 的转换质量门和清洗规则。

2. **Docling 对比路线**
   - 不直接替换 MinerU。
   - 新增 `docling_candidate` route，在真实样本上和 MinerU、现有 Office XML、现有 EPUB 路线对比。
   - 通过黄金样本后，再决定哪些格式默认走 Docling。

3. **转换评估工具层**
   - 先建 route registry 和 comparison report。
   - 这比马上接更多工具更重要。

### 8.2 第二批推荐接入

1. **PaddleOCR standalone image route**
   - 只针对独立图片输入。
   - 先做图片 OCR 黄金样本，不通过前保持 unsupported。

2. **yt-dlp subtitle route**
   - 只下载字幕或元数据，不默认下载视频。
   - 输出 `.vtt` 或 `.srt` 后进入现有字幕流程。

3. **faster-whisper 或 whisper.cpp ASR route**
   - 用于无字幕音视频。
   - 必须 optional 安装，不影响普通文档用户。

### 8.3 暂不建议接入

1. **Unstructured 作为主路线**
   - 功能强，但偏大型 ETL，可能把 KBPrep 变重。
   - 可以保留为后续 benchmark 对照。

2. **Calibre 作为内置依赖**
   - 适合用户预处理 MOBI，但不适合轻量内置。

3. **EbookLib**
   - 许可证和收益不匹配，现阶段不优先。

## 9. 实施路线图

### 阶段 0：建立开发基线

目标：所有后续代理知道以什么为准。

任务：

1. 保持两份最高开发文件只读。
2. 本文作为执行路线，不替代最高设计文档。
3. 每次改动前先判断是否服务于质量流水线。

验收：

- `AGENTS.md` 已声明最高参考文件。
- 新增开发实施文档不改动最高设计文件。

### 阶段 1：转换路线注册表

目标：让每个转换工具都可解释、可替换、可验证。

任务：

1. 新增或扩展 route registry。
2. 每个 route 必须声明：
   - 支持格式。
   - 依赖。
   - 是否默认启用。
   - 输出产物。
   - 可保留的结构。
   - 已验证样本。
   - 失败时的下一步。
3. `diagnosis_report.json` 和 `conversion_report.json` 必须记录候选路线和实际路线。

验收：

- 同一个 PDF 能记录“为什么选 MinerU 或 PDF text layer”。
- HTML 能记录“为什么走 direct / trafilatura”。
- unsupported 不会进入伪转换。

### 阶段 2：黄金样本库

目标：用真实样本防止“看起来能转，其实丢了关键内容”。

任务：

1. 建立 `tests/fixtures/golden/` 或等价样本目录。
2. 每类样本至少包含：
   - 简单文档。
   - 表格。
   - 图片或图片引用。
   - 多级标题。
   - 代码或参数。
   - 噪音内容。
3. 每个样本定义必须保留的证据。

验收：

- partial 能力只有通过黄金样本后才能升级 verified。
- 新工具接入必须先跑黄金样本。

### 阶段 3：HTML/URL 正文提取

目标：把 HTML 从“粗读文本”升级为“网页正文提取 + 来源证据”。

推荐工具：Trafilatura。

任务：

1. 对本地 HTML 先做 Trafilatura route。
2. 远程 URL 先做保守设计：下载 HTML、保存原始证据、再提取正文。
3. 输出 metadata：标题、URL、抓取时间、正文提取工具。
4. 失败时保留原 HTML 和错误说明。

验收：

- 导航、页脚、cookie、广告不应进入最终正文。
- 正文标题、链接、列表应保留。
- URL 失败时不生成假 Markdown。

### 阶段 4：Docling/MinerU/现有路线对比

目标：选工具要靠样本结果，不靠名气。

任务：

1. 对 PDF、DOCX、PPTX、XLSX、EPUB 建立 comparison command。
2. 同一文件分别跑：
   - current route。
   - MinerU。
   - Docling。
   - 必要时 Pandoc 或 MarkItDown。
3. 输出比较报告：
   - 标题保留率。
   - 表格保留率。
   - 图片引用保留率。
   - 代码/参数保留率。
   - 乱码率。
   - 输出长度异常。
   - 人工复查建议。

验收：

- 不能因为某工具输出更漂亮就默认采用。
- 默认路线必须在黄金样本上更稳定。

### 阶段 5：分块级质量闭环

目标：把失败从“整份文件失败”推进到“哪个块失败、怎么修”。

任务：

1. `quality_report.json` 增加失败块列表。
2. `quality_tasks` 绑定具体 block_id、chunk、规则文件、转换产物。
3. 对清洗误删、广告残留、表格断裂、代码断裂分别给出动作。
4. 复跑时记录复跑范围。

验收：

- 用户能知道：失败在转换、分块、清洗还是合并。
- 修复任务不能只写“优化规则”。
- 每个任务必须有可复查方式。

### 阶段 6：受影响部分复跑

目标：减少大文档反复全量跑，降低时间和误伤。

任务：

1. 规则变更后，找到受影响的 source/run/block。
2. 对清洗类变更优先复跑 block/chunk。
3. 对转换类变更复跑文件。
4. 复跑结果再次进入质量门。

验收：

- 清洗规则变更不应无条件全量重跑 OCR。
- 复跑不能扩大到无关资料。
- 修复不能引入新误删或新残留。

### 阶段 7：图片和音视频输入

目标：只在文档路线稳定后扩展多媒体。

图片路线：

- 首选：Docling 或 MinerU 是否已能覆盖。
- 备选：PaddleOCR standalone。
- 输出必须包含 OCR 文本、图片证据、坐标或页序信息。

音视频路线：

- 有字幕：yt-dlp 获取字幕，进入现有字幕流程。
- 无字幕：faster-whisper 或 whisper.cpp 生成转写，再进入字幕/转写流程。

验收：

- 图片 OCR 不通过质量门时不能发布。
- 音视频转写必须标记 ASR 来源和可能错误。
- 平台链接必须提示版权、登录、网络失败和站点限制。

## 10. 推荐开发顺序

第一优先级：

1. 路线注册表和转换对比报告。
2. 黄金样本库。
3. Trafilatura HTML route。
4. Docling candidate route。

第二优先级：

1. PDF/Office/EPUB route 质量升级。
2. 分块级失败定位。
3. 规则变更后的受影响复跑。

第三优先级：

1. 图片 OCR。
2. 平台字幕抓取。
3. 音视频 ASR。
4. 旧 Office/MOBI 外部预转换工作流。

## 11. 每次开发的验收模板

每个小任务完成后，必须回答：

1. 改了什么。
2. 为什么改。
3. 哪条主流程受影响。
4. 哪些输入格式受影响。
5. 是否引入新依赖。
6. 失败时是否会明确提示，而不是假装成功。
7. 运行了哪些检查。
8. 用户如何手动验收。

推荐检查命令：

```bash
npm run build
npm run pack:check
npm test
python -m unittest discover -s python/tests
```

如果是重型工具或 OCR 变更，还应补充真实样本验收：

```bash
kbprep-analyze --input <sample>
kbprep-prepare --input <sample> --output <out> --force
```

用户验收时重点看：

- `quality_report.json`
- `converted.md`
- `cleaned.md`
- `discarded.md`
- `review_needed.md`
- 最终 Markdown 或 Obsidian 目录

## 12. 风险提示

1. 不要把“能输出 Markdown”误认为“能进知识库”。
2. 不要让 Docling、MinerU、MarkItDown、Pandoc 任何一个工具直接绕过质量门。
3. 不要默认接入所有重依赖，否则本地安装和维护会变复杂。
4. 不要把网页抓取、平台下载、音视频转写做成默认能力；这些涉及版权、登录、网络和失败恢复。
5. 不要把用户反馈直接写进长期规则；必须有例子、反例和确认。

## 13. 当前结论

KBPrep 当前最值得做的不是“再多支持几个格式”，而是先把工具接入方式标准化：

> 外部工具负责尽量高质量转换；KBPrep 负责路线选择、证据保留、质量门、规则清洗、失败定位、复跑和最终发布。

下一步建议从 **Trafilatura HTML route + Docling candidate route + 转换对比报告 + 黄金样本库** 开始。这样既能快速提升真实资料处理能力，又不会破坏现有可演示闭环。

## 14. 调查来源

- MinerU GitHub: https://github.com/opendatalab/MinerU
- Docling GitHub: https://github.com/docling-project/docling
- MarkItDown GitHub: https://github.com/microsoft/markitdown
- Unstructured GitHub: https://github.com/Unstructured-IO/unstructured
- Pandoc GitHub: https://github.com/jgm/pandoc
- Trafilatura GitHub: https://github.com/adbar/trafilatura
- PaddleOCR GitHub: https://github.com/PaddlePaddle/PaddleOCR
- yt-dlp GitHub: https://github.com/yt-dlp/yt-dlp
- faster-whisper GitHub: https://github.com/SYSTRAN/faster-whisper
- whisper.cpp GitHub: https://github.com/ggml-org/whisper.cpp
- Mammoth.js GitHub: https://github.com/mwilliamson/mammoth.js
- Calibre GitHub: https://github.com/kovidgoyal/calibre
