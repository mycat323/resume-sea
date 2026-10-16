#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
convert.py — 简历海转换工具（CLI 主编排）

流水线：
  简历文件(PDF/Word) ──parsers──> 纯文本 ──extractor──> RSUF 统一格式 JSON
      │                                                    │  (可手工编辑后重渲染)
      └────────────── --from-json ─────────────────────────┘
                                                           ▼
                              adapters ──> 模板数据 ──build.js(Node)──> 静态站点
                                                           ▼
                                    发布到 <平台根>/<name>/ 并更新注册表

用法示例：
  # 从 Word 简历转换并发布为 testresume1
  python convert.py ../samples/sample-resume.docx --name testresume1 --skin blue

  # 从 PDF 转换
  python convert.py ~/Documents/张三-前端工程师.pdf --name zhangsan

  # 编辑过统一 JSON 后重新渲染发布（跳过解析）
  python convert.py --from-json ../resumes/testresume1.rsuf.json --name testresume1

  # 附带头像（建议 100x100 以上正方形）
  python convert.py resume.docx --name testresume1 --avatar photo.jpg

  # 查看可用模板
  python convert.py --list-templates
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)          # 平台仓库根目录
TEMPLATES_DIR = os.path.join(TOOLS_DIR, "templates")
RESUMES_DIR = os.path.join(REPO_ROOT, "resumes")
REGISTRY_FILE = os.path.join(RESUMES_DIR, "registry.json")
BUILD_DIR = os.path.join(TOOLS_DIR, ".build")
# 已发布简历的统一输出目录：<仓库根>/docs/<name>/
# 放在 docs/ 下便于 GitHub Pages 直接以该目录或仓库根为源发布。
PUBLISH_DIR = os.path.join(REPO_ROOT, "docs")

sys.path.insert(0, TOOLS_DIR)
from parsers import parse_resume            # noqa: E402
from extractor import extract_resume        # noqa: E402
from adapters import adapt                  # noqa: E402


# ---------------------------------------------------------------- 工具函数

def find_node():
    """定位 Node 可执行文件：命令行参数 > 环境变量 > PATH > WorkBuddy 托管运行时"""
    candidates = []
    if os.environ.get("RESUME_SEA_NODE"):
        candidates.append(os.environ["RESUME_SEA_NODE"])
    which = shutil.which("node")
    if which:
        candidates.append(which)
    candidates += sorted(
        glob.glob(os.path.expanduser("~/.workbuddy/binaries/node/versions/*/node.exe")),
        reverse=True,
    )
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def find_node_modules():
    """定位 liquidjs/js-yaml/sass/marked 所在 node_modules 目录"""
    candidates = []
    if os.environ.get("RESUME_SEA_NODE_MODULES"):
        candidates.append(os.environ["RESUME_SEA_NODE_MODULES"])
    candidates.append(os.path.expanduser("~/.workbuddy/binaries/node/envs/cv-render/node_modules"))
    candidates.append(os.path.join(TOOLS_DIR, "node_modules"))
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "liquidjs")):
            return c
    return None


def load_registry():
    if os.path.isfile(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"platform": "简历海 resume-sea", "base_url": "", "resumes": []}


def save_registry(reg):
    os.makedirs(RESUMES_DIR, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def update_registry(name, template, skin, source, confidence):
    reg = load_registry()
    # 去掉 base_url 末尾斜杠后拼接，不能用 .replace("//", "/")：
    # 那会把 scheme 的 "https://" 一并破坏成 "https:/"。
    base_url = (reg.get("base_url") or "").rstrip("/")
    entry = {
        "id": name,
        "title": "",
        "template": template,
        "skin": skin,
        "source": os.path.basename(source) if source else "",
        "confidence": confidence,
        "published_at": __import__("datetime").date.today().isoformat(),
        "url": f"{base_url}/docs/{name}",
    }
    # title 从 RSUF 读取（调用方传入的 name 之前已落盘）
    rsuf_path = os.path.join(RESUMES_DIR, f"{name}.rsuf.json")
    if os.path.isfile(rsuf_path):
        with open(rsuf_path, "r", encoding="utf-8") as f:
            rsuf = json.load(f)
        entry["title"] = f"{rsuf.get('basic', {}).get('name', name)}的简历"

    resumes = [r for r in reg.get("resumes", []) if r.get("id") != name]
    resumes.append(entry)
    reg["resumes"] = sorted(resumes, key=lambda r: r.get("published_at", ""), reverse=True)
    save_registry(reg)
    return entry


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(
        description="简历海转换工具：PDF/Word 简历 -> 统一格式 -> 模板静态站点",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("input", nargs="?", help="简历文件路径（.pdf/.docx/.txt/.md）")
    ap.add_argument("--name", required=True, help="发布路径名（URL 片段），如 testresume1")
    ap.add_argument("--template", default="online-cv", help="模板名（默认 online-cv）")
    ap.add_argument("--skin", default="blue",
                    help="配色皮肤：blue/turquoise/green/berry/orange/ceramic/teal/oceanstale")
    ap.add_argument("--avatar", help="头像图片路径（将部署为 assets/images/profile.png）")
    ap.add_argument("--from-json", dest="from_json",
                    help="从已编辑的 RSUF 统一 JSON 渲染（跳过文件解析）")
    ap.add_argument("--analytics", help="可选：Google Analytics ID（默认不注入）")
    ap.add_argument("--list-templates", action="store_true", help="列出可用模板")
    args = ap.parse_args()

    # ---- 模板列表 ----
    if args.list_templates:
        for d in sorted(os.listdir(TEMPLATES_DIR)):
            tpl_dir = os.path.join(TEMPLATES_DIR, d)
            if os.path.isdir(tpl_dir):
                readme = os.path.join(tpl_dir, "README.md")
                desc = ""
                if os.path.isfile(readme):
                    with open(readme, "r", encoding="utf-8") as f:
                        first = f.readline().lstrip("# ").strip()
                    desc = first
                print(f"  {d:<12} {desc}")
        return

    if not args.name or not args.name.replace("-", "").replace("_", "").isalnum():
        print("[错误] --name 只能包含字母、数字、- 和 _（将作为 URL 路径）", file=sys.stderr)
        sys.exit(2)

    template_dir = os.path.join(TEMPLATES_DIR, args.template)
    if not os.path.isdir(template_dir):
        print(f"[错误] 模板不存在: {args.template}，可用模板见 --list-templates", file=sys.stderr)
        sys.exit(2)

    os.makedirs(RESUMES_DIR, exist_ok=True)
    rsuf_path = os.path.join(RESUMES_DIR, f"{args.name}.rsuf.json")

    # ---- 1. 获取 RSUF 统一格式 ----
    if args.from_json:
        print(f"[1/5] 读取统一格式 JSON: {args.from_json}")
        with open(args.from_json, "r", encoding="utf-8") as f:
            rsuf = json.load(f)
    else:
        if not args.input:
            print("[错误] 需要提供简历文件，或使用 --from-json", file=sys.stderr)
            sys.exit(2)
        print(f"[1/5] 解析简历文件: {args.input}")
        text = parse_resume(args.input)
        print(f"      提取文本 {len(text)} 字符")
        rsuf = extract_resume(text, source_file=os.path.basename(args.input))

    with open(rsuf_path, "w", encoding="utf-8") as f:
        json.dump(rsuf, f, ensure_ascii=False, indent=2)
    conf = rsuf.get("meta", {}).get("confidence", 0)
    print(f"[2/5] 统一格式已保存: {rsuf_path}（置信度 {conf}）")
    if conf < 0.6:
        print("      [提示] 置信度偏低，建议打开上面的 JSON 校对后再用 --from-json 重新发布")

    # ---- 2. 适配为模板数据 ----
    site_data = adapt(rsuf, args.template, skin=args.skin)
    os.makedirs(BUILD_DIR, exist_ok=True)
    data_file = os.path.join(BUILD_DIR, f"{args.name}.data.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(site_data, f, ensure_ascii=False, indent=2)

    # ---- 3. Node 渲染静态站点 ----
    node = find_node()
    node_modules = find_node_modules()
    if not node:
        print("[错误] 未找到 Node.js。请安装 Node 或设置 RESUME_SEA_NODE 环境变量", file=sys.stderr)
        sys.exit(2)
    if not node_modules:
        print("[错误] 未找到渲染依赖（liquidjs/js-yaml/sass/marked）。\n"
              "       请在 tools/ 目录执行: npm install liquidjs js-yaml sass marked\n"
              "       或设置 RESUME_SEA_NODE_MODULES 指向依赖所在 node_modules", file=sys.stderr)
        sys.exit(2)

    out_dir = os.path.join(PUBLISH_DIR, args.name)
    env = dict(os.environ)
    env["NODE_PATH"] = node_modules
    cmd = [
        node,
        os.path.join(TOOLS_DIR, "render", "build.js"),
        "--template", template_dir,
        "--data", data_file,
        "--out", out_dir,
        "--skin", args.skin,
    ]
    if args.analytics:
        cmd += ["--analytics", args.analytics]

    print(f"[3/5] 渲染模板 {args.template}（皮肤 {args.skin}）-> {out_dir}")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        print("[错误] 渲染失败", file=sys.stderr)
        sys.exit(1)
    print(r.stdout.strip())

    # ---- 4. 头像 ----
    if args.avatar:
        dest = os.path.join(out_dir, "assets", "images", "profile.png")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(args.avatar, dest)
        print(f"[4/5] 头像已部署: {args.avatar} -> assets/images/profile.png")
    else:
        print("[4/5] 未提供头像（使用模板默认头像，可稍后替换 <发布目录>/assets/images/profile.png）")

    # ---- 5. 更新注册表 ----
    entry = update_registry(args.name, args.template, args.skin, args.input, conf)
    print(f"[5/5] 注册表已更新: resumes/registry.json -> {entry['title'] or args.name}")

    print("\n完成！本地预览（在仓库根目录执行）：")
    print("  python -m http.server 4000")
    print(f"  打开 http://localhost:4000/docs/{args.name}/")
    print("发布到 GitHub Pages：")
    print("  git add . && git commit -m \"publish: " + args.name + "\" && git push")
    print(f"  线上地址: https://mycat323.github.io/resume-sea/docs/{args.name}")


if __name__ == "__main__":
    main()
