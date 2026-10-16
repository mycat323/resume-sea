#!/usr/bin/env node
/**
 * build.js — 简历海模板渲染引擎（Node 复刻 Jekyll 构建，无需 Ruby）
 *
 * 用法：
 *   node build.js --template <模板目录> --data <site-data.json> --out <输出目录>
 *                [--skin blue] [--analytics UA-XXX]
 *
 * 说明：
 *   --template  模板目录（含 _layouts/_includes/_sass/assets/index.html/print.html）
 *   --data      模板数据 JSON（由 adapters 从 RSUF 统一格式转换而来）
 *   --skin      配色皮肤（online-cv 支持 blue/turquoise/green/berry/orange/ceramic/teal/oceanstale）
 *   --analytics 可选，Google Analytics ID；默认不注入（避免继承模板作者的统计代码）
 *
 * 依赖：liquidjs / js-yaml / sass / marked（见 convert.py 中的 NODE_PATH 配置）
 */
'use strict';

const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');
const { Liquid } = require('liquidjs');
const marked = require('marked');
const sass = require('sass');

// ---------- 参数解析 ----------
function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, '');
    args[key] = argv[i + 1];
  }
  return args;
}
const args = parseArgs(process.argv);
const ROOT = path.resolve(args.template || '.');
const DATA_FILE = path.resolve(args.data);
const OUT = path.resolve(args.out);

if (!fs.existsSync(DATA_FILE)) {
  console.error('找不到数据文件: ' + DATA_FILE);
  process.exit(1);
}

// ---------- 配置与数据 ----------
let templateConfig = {};
const configPath = path.join(ROOT, '_config.yml');
if (fs.existsSync(configPath)) {
  templateConfig = yaml.load(fs.readFileSync(configPath, 'utf8')) || {};
}
const siteData = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));

const site = Object.assign({}, templateConfig, {
  // baseurl 由 renderPage 按输出深度动态计算：
  //   根级页面 -> '.'（./assets/...）
  //   子目录页面 -> '..'（../assets/...）
  // 这样本地预览（http://localhost:xxxx/<name>/）与 GitHub Pages
  // 子路径部署（https://<user>.github.io/<repo>/<name>/）都能正确解析资源。
  baseurl: '.',
  data: { data: siteData },
  theme_skin: args.skin || templateConfig.theme_skin || 'blue',
  analytics: args.analytics || null, // 默认关闭，防止继承模板作者的 GA ID
});

// ---------- Liquid 引擎 ----------
const engine = new Liquid({ strictVariables: false });
engine.registerFilter('markdownify', (input) => {
  const text = input == null ? '' : String(input);
  return marked.parse(text, { gfm: true, breaks: false }).trim();
});

// ---------- front matter / include / layout ----------
function splitFrontMatter(raw) {
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!m) return { front: {}, body: raw };
  let front = {};
  try { front = yaml.load(m[1]) || {}; } catch (e) { /* 忽略 */ }
  return { front, body: raw.slice(m[0].length) };
}

function inlineIncludes(tpl, depth) {
  if (depth === undefined) depth = 0;
  if (depth > 12) throw new Error('include 递归层数过多');
  return tpl.replace(
    /\{%-?\s*include\s+(['"]?)([^'"%\s]+)\1[^%]*-?%\}/g,
    (match, q, name) => {
      const p = path.join(ROOT, '_includes', name);
      if (!fs.existsSync(p)) throw new Error('找不到 include: ' + name);
      return inlineIncludes(fs.readFileSync(p, 'utf8'), depth + 1);
    }
  );
}

async function renderPage(file, outputs) {
  const raw = fs.readFileSync(path.join(ROOT, file), 'utf8');
  const { front, body } = splitFrontMatter(raw);

  let html = body;
  let layoutName = front.layout;
  const guard = new Set();
  while (layoutName) {
    if (guard.has(layoutName)) throw new Error('layout 循环: ' + layoutName);
    guard.add(layoutName);
    const lp = path.join(ROOT, '_layouts', layoutName + '.html');
    if (!fs.existsSync(lp)) throw new Error('找不到 layout: ' + layoutName);
    const l = splitFrontMatter(fs.readFileSync(lp, 'utf8'));
    html = l.body.replace(/\{\{\s*content\s*\}\}/g, () => html);
    layoutName = l.front.layout;
  }

  html = inlineIncludes(html);
  const pageCtx = Object.assign({}, front);
  delete pageCtx.layout;
  for (const out of outputs) {
    // 按输出文件的目录深度计算相对前缀，保证子目录页面（如 print/）资源路径正确
    const depth = out.split(/[\\/]/).length - 1;
    site.baseurl = depth === 0 ? '.' : new Array(depth).fill('..').join('/');
    const rendered = await engine.parseAndRender(html, { site, page: pageCtx });
    const dest = path.join(OUT, out);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, rendered);
    console.log('[page] ' + file + ' -> ' + out + ' (baseurl=' + site.baseurl + ', ' + rendered.length + ' bytes)');
  }
}

// ---------- SCSS：先渲染 Liquid（动态皮肤）再编译 ----------
function buildCss() {
  const scssPath = path.join(ROOT, 'assets', 'css', 'main.scss');
  let raw = fs.readFileSync(scssPath, 'utf8');
  raw = raw.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '');
  site.baseurl = '.'; // SCSS 内不引用 baseurl，置回默认值避免污染
  const liquidRendered = engine.parseAndRenderSync(raw, { site });
  const result = sass.compileString(liquidRendered, {
    loadPaths: [path.join(ROOT, '_sass'), path.join(ROOT, 'assets', 'css')],
    style: 'compressed',
    quietDeps: true,
  });
  const dest = path.join(OUT, 'assets', 'css', 'main.css');
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, result.css);
  console.log('[css ] skin=' + site.theme_skin + ' -> assets/css/main.css (' + result.css.length + ' bytes)');
}

// ---------- 静态资源 ----------
function copyDir(src, dest, skip) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (skip && skip(entry, src)) continue;
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d, skip);
    else fs.copyFileSync(s, d);
  }
}

function copyAssets() {
  const assetsRoot = path.join(ROOT, 'assets');
  // 仅跳过顶层 assets/css（由 buildCss 编译产出）；plugins 下的 css 目录必须保留
  copyDir(assetsRoot, path.join(OUT, 'assets'), (e, src) => {
    if (src === assetsRoot && e.isDirectory() && e.name === 'css') return true;
    return false;
  });
  fs.mkdirSync(path.join(OUT, 'assets', 'css'), { recursive: true });
  const fav = path.join(ROOT, 'favicon.ico');
  if (fs.existsSync(fav)) fs.copyFileSync(fav, path.join(OUT, 'favicon.ico'));
}

// ---------- 主流程 ----------
(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  await renderPage('index.html', ['index.html']);
  await renderPage('print.html', [path.join('print', 'index.html')]);
  buildCss();
  copyAssets();
  console.log('渲染完成 -> ' + OUT);
})().catch((e) => {
  console.error('渲染失败: ' + e.message);
  process.exit(1);
});
