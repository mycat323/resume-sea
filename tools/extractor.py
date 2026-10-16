# -*- coding: utf-8 -*-
"""
extractor.py — 启发式简历结构化抽取器

输入 parsers 得到的纯文本，输出 RSUF（简历海统一格式）JSON 字典。

适用对象：常规单栏中文简历（Word/文字版 PDF），中英文关键词混合识别。
局限说明：简历排版千差万别，启发式规则无法保证 100% 准确；
因此本工具采用「机器抽取 + JSON 中间产物 + 人工校对」工作流：
  1. convert.py 先抽出统一 JSON（可手工修改）
  2. 用 --from-json 重新渲染发布
meta.confidence 反映本次抽取的完整度，低于 0.6 时建议人工校对。
"""
import re
from datetime import datetime

# ---------------------------------------------------------------- 基础工具

def _clean_lines(text):
    """去首尾空白；保留行内多空格（简历常用双空格分隔字段）。"""
    lines = []
    for raw in text.splitlines():
        line = raw.strip().strip("\u3000").strip()
        if line:
            lines.append(line)
    return lines


# 注意：连字符必须放末尾或转义，否则 *-– 会形成巨大字符范围（历史 bug）
BULLET_RE = re.compile(r"^[•·●▪◆*\-–—>]\s*")
def _strip_bullet(line):
    return BULLET_RE.sub("", line).strip()


def _is_bullet(line):
    return bool(BULLET_RE.match(line))


DATE_RE = re.compile(
    r"(?P<y1>\d{4})\s*[.\-/年]\s*(?P<m1>\d{1,2})?\s*月?\s*"
    r"(?:[-–—~～至到]|\bto\b)\s*"
    r"(?:(?P<y2>\d{4})\s*[.\-/年]\s*(?P<m2>\d{1,2})?\s*月?|(?P<now>至今|现在|now|present|Present))"
)
SINGLE_DATE_RE = re.compile(r"(?<!\d)(\d{4})\s*[.\-/年]\s*(\d{1,2})\s*月?(?!\d)")


def _fmt_date(m):
    y1, m1, y2, m2, now = m.group("y1"), m.group("m1"), m.group("y2"), m.group("m2"), m.group("now")
    start = f"{y1}.{int(m1):02d}" if m1 else y1
    end = "至今" if now else (f"{y2}.{int(m2):02d}" if m2 else y2)
    return start, end


def _find_dates(line):
    return [_fmt_date(m) for m in DATE_RE.finditer(line)]


def _remove_dates(line):
    return DATE_RE.sub(" ", line).strip(" -–—~～至到|,，、")


# ---------------------------------------------------------------- 章节识别

SECTION_PATTERNS = [
    ("summary",        r"^(个人简介|自我评价|个人评价|自我介绍|个人描述|summary|profile)$"),
    ("education",      r"^(教育经历|教育背景|教育培训|教育|学历|education)$"),
    ("experience",     r"^(工作经历|工作经验|实习经历|工作履历|职业经历|任职经历|work\s*experience|experience)$"),
    ("projects",       r"^(项目经历|项目经验|项目|projects?)$"),
    ("skills",         r"^(专业技能|技术栈|技能清单|核心技能|技能|technical\s*skills|skills?)$"),
    ("certifications", r"^(资格证书|证书与荣誉|证书|荣誉奖项|获奖情况|奖项|certifications?|awards?|honors?)$"),
    ("languages",      r"^(语言|语言能力|languages?)$"),
]

def _section_of(line):
    s = re.sub(r"^[#\s【\[\(（]+|[】\]\)）\s]+$", "", line).strip()
    s = re.sub(r"^[一二三四五六七八九十\d]+[、.．]?\s*", "", s)
    for name, pat in SECTION_PATTERNS:
        if re.match(pat, s, re.I):
            return name
    return None


def split_sections(lines):
    """返回 {section: [lines...]} 与 header 区行列表。"""
    header, sections, current = [], {}, None
    for line in lines:
        if line.startswith("## "):  # docx 标题样式标记
            current = _section_of(line[3:]) or current
            continue
        sec = _section_of(line)
        if sec and len(line) <= 20:
            current = sec
            sections.setdefault(current, [])
            continue
        if current is None:
            header.append(line)
        else:
            sections.setdefault(current, []).append(line)
    return header, sections


# ---------------------------------------------------------------- 头部信息

CONTACT_PATTERNS = {
    "email":    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    # 手机号允许 - / 空格分隔（138-0013-8000）
    "phone":    re.compile(r"(?<![\d-])(?:\+?86[-.\s]?)?1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}(?![\d-])"),
    "github":   re.compile(r"(?:github\.com/)([A-Za-z0-9_-]+)", re.I),
    "linkedin": re.compile(r"(?:linkedin\.com/in/)([A-Za-z0-9_-]+)", re.I),
    "website":  re.compile(r"(?<![@\w])(https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s,，|]*)?)"),
    "wechat":   re.compile(r"(?:微信|wechat)[:：]?\s*([A-Za-z0-9_-]{5,20})", re.I),
}

NAME_RE = re.compile(r"^[\u4e00-\u9fa5]{2,4}$|^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}$")
ROLE_RE = re.compile(
    r"工程师|开发|经理|主管|总监|设计师|研究员|助理|实习生|顾问|架构师|负责人|专家|"
    r"engineer|developer|manager|designer|intern|architect|lead", re.I)
HEADLINE_RE = re.compile(r"求职意向|应聘岗位|target\s*position", re.I)
CITY_RE = re.compile(r"(现居|所在地|地址|location)[:：]?\s*([^\s,，|]{2,20})", re.I)


def parse_header(header_lines):
    basic, contacts = {}, {}
    text = "\n".join(header_lines)

    # ---- 姓名 ----
    m = re.search(r"姓\s*名[:：]?\s*(\S+)", text)
    if m:
        basic["name"] = m.group(1).strip()
    else:
        for line in header_lines[:6]:
            cand = re.sub(r"[|·\s].*$", "", line).strip()
            if NAME_RE.match(cand) and not CONTACT_PATTERNS["email"].search(line) \
               and not CONTACT_PATTERNS["phone"].search(line) and len(cand) >= 2:
                basic["name"] = cand
                break

    # ---- 头衔 ----
    m = re.search(HEADLINE_RE.pattern + r"[:：]?\s*([^\n,，|]{2,30})", text, re.I)
    if m:
        basic["headline"] = m.group(1).strip()
    else:
        for line in header_lines[:6]:
            if line == basic.get("name"):
                continue
            if ROLE_RE.search(line) and len(line) <= 30 \
               and not CONTACT_PATTERNS["email"].search(line) \
               and not CONTACT_PATTERNS["phone"].search(line):
                basic["headline"] = line.strip(" |·,，")
                break

    # ---- 城市 ----
    m = CITY_RE.search(text)
    if m:
        basic["location"] = m.group(2).strip()
    else:
        m = re.search(r"([\u4e00-\u9fa5]{2,8}(?:市|区))(?![\u4e00-\u9fa5])", text)
        if m:
            basic["location"] = m.group(1)

    # ---- 联系方式 ----
    m = CONTACT_PATTERNS["email"].search(text)
    if m:
        contacts["email"] = m.group(0)
    m = CONTACT_PATTERNS["phone"].search(text)
    if m:
        contacts["phone"] = re.sub(r"\D", "", m.group(0))  # 归一化为纯数字
    m = CONTACT_PATTERNS["github"].search(text)
    if m:
        contacts["github"] = m.group(1)
    m = CONTACT_PATTERNS["linkedin"].search(text)
    if m:
        contacts["linkedin"] = m.group(1)
    m = CONTACT_PATTERNS["wechat"].search(text)
    if m:
        contacts["wechat"] = m.group(1)
    m = CONTACT_PATTERNS["website"].search(text)
    if m:
        contacts["website"] = m.group(1)

    return basic, contacts


# ---------------------------------------------------------------- 各章节解析

SCHOOL_NAME_RE = re.compile(
    r"[\u4e00-\u9fa5A-Za-z()（）]{2,15}?(?:大学|学院|学校|中学|University|College|Institute)", re.I)
DEGREE_RE = re.compile(
    r"本科|学士|硕士|博士|研究生|专科|MBA|EMBA|Bachelor|Master|PhD|B\.?S\.?|M\.?S\.?", re.I)
COMPANY_RE = re.compile(
    r"公司|集团|科技|有限|股份|事业部|工作室|实验室|银行|医院|院$|Inc\.?|Ltd\.?|LLC|Technologies|Corp", re.I)


def _split_by_dates(lines):
    """按时间区间把行切成条目块；无时间线的行归入上一个块或单独成块。"""
    blocks, current = [], []
    for line in lines:
        if _find_dates(line):
            if current:
                blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def parse_education(lines):
    entries = []
    for block in _split_by_dates(lines):
        text_lines = [_remove_dates(_strip_bullet(l)) for l in block]
        text_lines = [l for l in text_lines if l]
        if not text_lines:
            continue
        dates = _find_dates(block[0]) or [(None, None)]
        head = text_lines[0]

        school_m = SCHOOL_NAME_RE.search(head)
        school = school_m.group(0) if school_m else head.split(" ")[0]
        degree_m = DEGREE_RE.search(head)
        degree = degree_m.group(0) if degree_m else ""
        # 专业：去掉学校与学位词后的剩余内容
        major = DEGREE_RE.sub("", SCHOOL_NAME_RE.sub("", head)).strip(" ·|,，、-")
        if major:
            degree = f"{degree} · {major}" if degree else major
        if not degree:
            degree = next((l for l in text_lines[1:] if DEGREE_RE.search(l)), "")
        details = [l for l in text_lines[1:] if l != school]
        entries.append({
            "school": school.strip(" |,，、"),
            "degree": degree.strip(" |,，、"),
            "start": dates[0][0], "end": dates[0][1],
            "details": "\n".join(details),
        })
    return entries


def _split_company_role(head):
    """从 '公司  角色' 行中拆出公司与角色。支持 双空格/单空格/无分隔 三种写法。"""
    # 1) 显式分隔符
    parts = [p.strip() for p in re.split(r"[|｜]", head) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    # 2) 双空格（Word 常见）
    parts = [p.strip() for p in re.split(r"\s{2,}", head) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    # 3) 单空格且恰好两段
    parts = [p.strip() for p in head.split(" ") if p.strip()]
    if len(parts) == 2:
        return parts[0], parts[1]
    # 4) 多段：末段像职位则末段为角色，其余为公司
    if len(parts) > 2 and ROLE_RE.search(parts[-1]):
        return " ".join(parts[:-1]), parts[-1]
    # 5) 兜底：按职位关键词边界切分
    m = ROLE_RE.search(head)
    if m and m.start() > 0:
        return head[:m.start()].strip(" ,，、"), head[m.start():].strip()
    return head.strip(), ""


def parse_experience(lines):
    entries = []
    for block in _split_by_dates(lines):
        head = _remove_dates(_strip_bullet(block[0])).strip(" |,，、-")
        rest = [_strip_bullet(l) for l in block[1:]]
        dates = _find_dates(block[0]) or [(None, None)]

        company, role = _split_company_role(head)

        # 公司/角色常分行书写：在后续非条目行里继续找
        details = []
        for l in rest:
            if not company and COMPANY_RE.search(l) and len(l) <= 30:
                company = l
            elif not role and ROLE_RE.search(l) and len(l) <= 30:
                role = l
            else:
                details.append(l)

        if not (company or role):
            continue
        entries.append({
            "company": company, "role": role,
            "start": dates[0][0], "end": dates[0][1],
            "details": "\n".join(details),
        })
    return entries


def _looks_like_title(line):
    """项目名候选：短行、无句逗、非条目符号。"""
    if _is_bullet(line):
        return False
    s = _strip_bullet(line)
    if len(s) > 20:
        return False
    if re.search(r"[。，、；,.]", s):  # 标题通常不含逗号句号
        return False
    return True


def parse_projects(lines):
    """以“短标题行”切块：首个短行为项目名，紧随的非标题行为简介，其余为详情。"""
    entries, current = [], []
    for line in lines:
        if _looks_like_title(line) and current:
            entries.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(current)

    out = []
    for block in entries:
        name = _strip_bullet(block[0]).strip(" |,，、")
        tagline, details = "", []
        for l in block[1:]:
            if not tagline and not _is_bullet(l) and not _looks_like_title(l) and len(l) <= 60:
                tagline = _strip_bullet(l).strip()
            else:
                details.append(_strip_bullet(l).strip())
        if name:
            out.append({"name": name, "tagline": tagline, "link": "",
                        "start": None, "end": None, "details": "\n".join(details)})
    return out


LEVEL_MAP = [("精通", 95), ("expert", 95), ("熟练", 85), ("proficient", 85),
             ("掌握", 80), ("熟悉", 75), ("familiar", 75), ("了解", 60), ("knowledge", 60)]


def parse_skills(lines):
    skills, seen = [], set()

    def _add(name, level):
        name = name.strip(" .。:：、,，/|；;")
        if not name or len(name) > 30 or name.lower() in seen:
            return
        seen.add(name.lower())
        skills.append({"name": name, "level": level})

    for line in lines:
        body = _strip_bullet(line)
        level = 75
        for kw, lv in LEVEL_MAP:
            if re.search(kw, body, re.I):
                level = lv
                body = re.sub(r"^(精通|熟练|熟悉|掌握|了解|expert|proficient|familiar|knowledge)[:：]?\s*",
                              "", body, flags=re.I)
                break
        body = re.sub(r"^(技能|技术栈|编程语言|框架|工具)[:：]\s*", "", body, flags=re.I)
        for token in re.split(r"[、,，/|；;\s]+", body):
            if token and not re.fullmatch(r"[\W_]+", token):
                _add(token, level)
    return skills


def parse_certifications(lines):
    """支持 '名称  机构  2023.05' 与 '名称  机构  2021.03 - 2022.03' 两种写法。"""
    entries = []
    # 先按单日期切行，避免整段粘连
    expanded = []
    for line in lines:
        s = _strip_bullet(line)
        if SINGLE_DATE_RE.search(s) and not _find_dates(s):
            expanded.append(s)
        else:
            expanded.append(s)

    for line in expanded:
        if not line.strip():
            continue
        date = ""
        m = SINGLE_DATE_RE.search(line)
        if m and not _find_dates(line):
            date = f"{m.group(1)}.{int(m.group(2)):02d}"
            line = SINGLE_DATE_RE.sub(" ", line)
        else:
            m = DATE_RE.search(line)
            if m:
                date = " - ".join(x for x in _fmt_date(m) if x)
                line = _remove_dates(line)

        parts = [p.strip() for p in re.split(r"\s{2,}|[|｜]", line) if p.strip()]
        if not parts:
            continue
        name = parts[0].strip(" |,，、")
        org = parts[1] if len(parts) >= 2 else ""
        entries.append({"name": name, "org": org, "date": date, "details": ""})
    return entries


def _split_top_level(text):
    """按顶层分隔符切分（忽略括号内的分隔符），用于语言等枚举字段。"""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if depth == 0 and ch in "、,，/|；;":
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def parse_languages(lines):
    out = []
    text = " ".join(_strip_bullet(l) for l in lines)
    for seg in _split_top_level(text):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r"([\u4e00-\u9fa5A-Za-z]{2,10})\s*[（(]?\s*([^）)，,]{2,20})", seg)
        if m:
            out.append({"name": m.group(1), "level": m.group(2).strip()})
        elif re.match(r"^[\u4e00-\u9fa5A-Za-z]{2,10}$", seg):
            out.append({"name": seg, "level": ""})
    return out


# ---------------------------------------------------------------- 主入口

def extract_resume(text, source_file=""):
    lines = _clean_lines(text)
    header, sections = split_sections(lines)
    basic, contacts = parse_header(header)

    if sections.get("summary"):
        basic["summary"] = "\n\n".join(_strip_bullet(l) for l in sections["summary"])

    data = {
        "schema_version": "1.0",
        "basic": {k: v for k, v in basic.items() if v},
        "contacts": {k: v for k, v in contacts.items() if v},
        "education": parse_education(sections.get("education", [])),
        "experience": parse_experience(sections.get("experience", [])),
        "projects": parse_projects(sections.get("projects", [])),
        "skills": parse_skills(sections.get("skills", [])),
        "certifications": parse_certifications(sections.get("certifications", [])),
        "languages": parse_languages(sections.get("languages", [])),
    }

    # 置信度：按信息完整度加权
    weights = {"name": .15, "contact": .15, "education": .2, "experience": .25, "skills": .15, "projects": .1}
    got = sum([
        weights["name"] if basic.get("name") else 0,
        weights["contact"] if contacts else 0,
        weights["education"] if data["education"] else 0,
        weights["experience"] if data["experience"] else 0,
        weights["skills"] if data["skills"] else 0,
        weights["projects"] if data["projects"] else 0,
    ])
    data["meta"] = {
        "source_file": source_file,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "confidence": round(got, 2),
    }
    return data


if __name__ == "__main__":
    import json
    import sys
    from parsers import parse_resume

    if len(sys.argv) < 2:
        print("用法: python extractor.py <简历文件>", file=sys.stderr)
        sys.exit(2)
    txt = parse_resume(sys.argv[1])
    print(json.dumps(extract_resume(txt, sys.argv[1]), ensure_ascii=False, indent=2))
