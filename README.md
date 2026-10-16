# 简历海 resume-sea

> 把简历变成网址 —— 个人简历转换工具与统一发布平台

简历海是一个**简历转换 + 统一发布平台**：把 PDF / Word 简历转换成统一数据格式，
选择模板与配色，发布为独立网址的静态站点，基于 GitHub Pages 零成本托管。

| 页面 | 地址 |
| --- | --- |
| 平台首页 | https://mycat323.github.io/resume-sea/ |
| 模板库 | https://mycat323.github.io/resume-sea/template |
| 已发布简历（示例） | https://mycat323.github.io/resume-sea/docs/testresume |

## 模板基座选型结论

对工作区三个 Jekyll 简历主题评估后，**选用 `sharu725/online-cv`（Orbit 主题）作为第一个模板**：

| 候选 | 结论 | 理由 |
| --- | --- | --- |
| **sharu725/online-cv** | ✅ 采用 | 内容集中在 `_data/data.yml` **单一数据源**，字段化程度最高，与解析结果映射最直接；自带 `/print` 打印页与前端 PDF 导出；**8 种配色皮肤**一键切换，天然满足多模板诉求；生态成熟 |
| jekyller/PanelCV | ❌ 暂不 | 卡片式动态 vCard 效果好，但内容硬编码在 HTML 片段中，非数据驱动，程序化生成需先改造模板 |
| piazzai/cvless | 📋 规划中 | 学术极简风 + 博客 + 打印自适应，适合科研场景；Markdown 驱动面向手工维护，接入需补结构化适配器 |

三者模板源码已整理在 `../jekyller`、`../piazzai`、`../sharu725`，本平台模板副本位于 `tools/templates/online-cv/`。

## 架构与流水线

```
简历文件(.pdf/.docx)
   │  parsers.py        提取文字层（pypdf / python-docx）
   ▼
纯文本
   │  extractor.py      启发式结构化抽取（章节识别/日期/联系信息/技能分级）
   ▼
RSUF 统一格式 JSON  ──可人工校对──▶  --from-json 重新渲染
   │  adapters/         统一格式 → 模板数据（适配器模式，可扩展）
   ▼
模板数据 JSON
   │  render/build.js   Node 复刻 Jekyll 构建（liquidjs + sass + marked，无需 Ruby）
   ▼
静态站点 → docs/<name>/（index.html + print/ + assets/）
   │  convert.py        更新 resumes/registry.json 注册表
   ▼
git push → GitHub Pages 上线
```

## 快速开始

### 1. 安装依赖

```bash
# Python 解析依赖（任选一个国内镜像）
pip install -i https://mirrors.cloud.tencent.com/pypi/simple pypdf python-docx PyYAML

# Node 渲染依赖（ liquidjs / js-yaml / sass / marked ）
cd tools && npm install liquidjs js-yaml sass marked
```

### 2. 转换并发布

```bash
cd tools

# 从 Word 简历转换，发布为 testresume
python convert.py ../sample-cvs/sample-resume.docx --name testresume --skin blue

# 从 PDF 简历转换
python convert.py ~/Documents/张三-前端工程师.pdf --name zhangsan --skin teal

# 附带头像（建议 100x100 以上正方形，部署为 assets/images/profile.png）
python convert.py resume.docx --name myresume --avatar photo.jpg

# 校对过统一 JSON 后重新渲染（跳过解析）
python convert.py --from-json ../resumes/testresume.rsuf.json --name testresume

# 查看可用模板
python convert.py --list-templates
```

### 3. 本地预览

```bash
# 预览整个平台（首页 / 模板库 / 已发布简历）
cd .. && python -m http.server 4000
# http://localhost:4000/                  平台首页
# http://localhost:4000/template/         模板库
# http://localhost:4000/docs/testresume/  已发布简历

# 或只预览某一份简历
cd docs/testresume && python -m http.server 4000
```

### 4. 发布上线

```bash
git add . && git commit -m "publish: testresume" && git push
# GitHub Pages 自动部署 → https://mycat323.github.io/resume-sea/docs/testresume
```

> GitHub Pages 设置：仓库 Settings → Pages → Source 选 `main` 分支根目录。
> 注意：简历子目录是**预构建的静态站点**，不依赖 GitHub 的 Jekyll 构建。

## 统一数据格式（RSUF v1.0）

所有简历都会被规范化为 `tools/resume.schema.json` 定义的 JSON 结构：

```jsonc
{
  "schema_version": "1.0",
  "basic":       { "name": "陈雨桐", "headline": "前端开发工程师", "location": "上海", "summary": "…" },
  "contacts":    { "email": "…", "phone": "13800138000", "github": "cytong", "website": "…" },
  "education":   [{ "school": "同济大学", "degree": "本科 · 计算机科学与技术", "start": "2016.09", "end": "2020.06", "details": "…" }],
  "experience":  [{ "company": "字节跳动", "role": "高级前端开发工程师", "start": "2022.03", "end": "至今", "details": "…" }],
  "projects":    [{ "name": "简历海", "tagline": "…", "link": "…", "details": "…" }],
  "skills":      [{ "name": "Vue3", "level": 95 }],
  "certifications": [{ "name": "AWS …", "org": "Amazon", "date": "2023.05" }],
  "languages":   [{ "name": "中文", "level": "母语" }],
  "meta":        { "source_file": "…", "confidence": 1.0 }
}
```

- 抽取结果落在 `resumes/<name>.rsuf.json`，**可手工编辑**，满意后用 `--from-json` 重新发布
- `meta.confidence` 为抽取完整度（0–1），低于 0.6 时强烈建议人工校对
- 扫描件/图片型 PDF 无法提取文字，需先 OCR 或改用 Word 版

## 目录结构

```
resume-sea/
├── index.html              平台首页（动态加载注册表）
├── template/               模板库页面 + templates.json 清单 + 皮肤预览图
├── assets/css/style.css    平台样式
├── favicon.ico
├── resumes/
│   ├── registry.json       发布注册表（首页简历列表数据源）
│   └── *.rsuf.json         每份简历的统一格式中间产物
├── sample-cvs/             示例简历（DOCX + PDF，位于上级目录）
├── docs/                   已发布简历（静态站点，每份一个子目录）
│   ├── testresume/
│   └── jjc/
└── tools/
    ├── convert.py          转换工具 CLI 主编排
    ├── parsers.py          PDF/DOCX → 文本
    ├── extractor.py        文本 → RSUF 统一格式
    ├── resume.schema.json  RSUF 格式定义
    ├── make_sample.py      示例简历生成器
    ├── adapters/           模板适配器（online_cv.py）
    ├── render/build.js     Node 模板渲染引擎
    └── templates/online-cv/  online-cv 模板副本
```

## 新增模板

1. 将模板源码放入 `tools/templates/<模板名>/`（需含 `_layouts/_includes/_sass/assets/index.html/print.html`）
2. 在 `tools/adapters/` 新增适配器：RSUF → 模板数据，并注册到 `ADAPTERS`
3. 在 `template/templates.json` 登记模板信息与皮肤
4. `python convert.py resume.docx --name x --template <模板名>` 即可发布

## 已知限制

- 启发式抽取针对常规单栏中文简历优化，复杂排版（多栏/表格/图形化简历）准确率下降，以 JSON 校对兜底
- PDF 仅支持文字层，扫描件需 OCR 预处理
- 旧版 `.doc` 不支持，请另存为 `.docx`

## 许可与署名

- 平台代码：MIT
- 简历模板 Orbit：CC-BY 3.0，设计 © [3rd Wave Media](http://themes.3rdwavemedia.com)（发布页脚已保留署名）
