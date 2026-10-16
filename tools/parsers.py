# -*- coding: utf-8 -*-
"""
parsers.py — 将 PDF / Word 简历文件解析为纯文本行

支持：
  - .pdf  ：基于 pypdf 提取文字层（扫描件/图片型 PDF 无法处理，会抛出明确错误）
  - .docx ：基于 python-docx 提取段落与表格（按文档顺序输出）
  - .txt/.md：直接读取

设计原则：只负责“拿到文本”，不负责理解语义；语义抽取在 extractor.py。
"""
import os
import sys


def parse_pdf(path):
    """提取 PDF 文字层，返回文本。扫描件会返回空文本并报错。"""
    from pypdf import PdfReader

    reader = PdfReader(path)
    if reader.is_encrypted:
        try:
            reader.decrypt("")  # 尝试空密码解密
        except Exception as e:
            raise ValueError(f"PDF 已加密且无法自动解密: {e}")

    chunks = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception as e:
            print(f"[warn] 第 {i + 1} 页提取失败: {e}", file=sys.stderr)
            t = ""
        chunks.append(t)

    text = "\n".join(chunks).strip()
    if not text:
        raise ValueError(
            "PDF 中未提取到文字（可能是扫描件/图片型简历）。"
            "请改用 Word 版本，或先用 OCR 工具转为文字版 PDF。"
        )
    return text


def parse_docx(path):
    """按文档顺序提取 docx 的段落与表格内容。"""
    import docx
    from docx.document import Document as DocType
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.ns import qn

    doc = docx.Document(path)

    def iter_block_items(parent):
        """按 Body 顺序产出 Paragraph / Table（python-docx 官方推荐写法）。"""
        if isinstance(parent, DocType):
            parent_elm = parent.element.body
        else:
            parent_elm = parent._element
        for child in parent_elm.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    lines = []
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            t = block.text.strip()
            if t:
                # 附带样式名，抽取器可识别标题层级（如 Heading 1）
                style = (block.style.name or "").lower()
                if style.startswith("heading") or style.startswith("标题"):
                    lines.append(f"## {t}")  # 标记为标题行
                else:
                    lines.append(t)
        elif isinstance(block, Table):
            # 表格简历：每行合并单元格文本
            for row in block.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                # 去掉因合并单元格导致的重复
                dedup = []
                for c in cells:
                    if not dedup or dedup[-1] != c:
                        dedup.append(c)
                line = " | ".join(x for x in dedup if x)
                if line.strip(" |"):
                    lines.append(line)
    return "\n".join(lines)


def parse_text(path):
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_resume(path):
    """统一入口：根据扩展名选择解析器，返回文本。"""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(path)
    if ext in (".docx", ".doc"):
        if ext == ".doc":
            raise ValueError("暂不支持旧版 .doc 格式，请另存为 .docx 后重试")
        return parse_docx(path)
    if ext in (".txt", ".md"):
        return parse_text(path)
    raise ValueError(f"不支持的文件类型: {ext}（支持 .pdf / .docx / .txt / .md）")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python parsers.py <简历文件>", file=sys.stderr)
        sys.exit(2)
    print(parse_resume(sys.argv[1]))
