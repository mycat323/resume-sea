# -*- coding: utf-8 -*-
"""
adapters/online_cv.py — 将 RSUF 统一格式转换为 online-cv(Orbit) 模板的 data.yml 结构

转换策略：
  - 只做字段映射与格式化，不做内容生成（缺失字段直接省略，模板会自动隐藏对应区块）
  - education/experience 的时间合并为 "start - end" 字符串
  - skills.level(0-100) 转为模板需要的 "98%" 宽度字符串
  - 保留主题作者署名（CC-BY 3.0 许可要求）
"""
import os


def _time_range(start, end):
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def _prune(d):
    """删除值为空字符串/None 的键。

    必须显式删除而不能留空串：LiquidJS 把 "" 判为真值，模板里的
    {% if x %} 会因此渲染出 <a href=""> / href="//" 等无效锚点。
    """
    return {k: v for k, v in d.items() if v not in ("", None)}


def to_online_cv(rsuf, skin="blue", sidebar_position="right"):
    basic = rsuf.get("basic", {})
    contacts = rsuf.get("contacts", {})

    sidebar = {
        "position": sidebar_position,
        "about": False,          # 关闭“如何使用本主题”侧栏块
        "education": True,       # 教育经历放侧栏
        "name": basic.get("name", ""),
        "tagline": basic.get("headline", ""),
        # 侧栏头像固定取 assets/images/profile.png：模板自带该默认头像，
        # convert.py --avatar 也把用户头像覆盖写入同一路径。
        # 这里必须显式赋值，否则 sidebar.html 的 {% if sidebar.avatar %} 恒为假，
        # 用户提供的头像永远不会被渲染。
        "avatar": "profile.png",
    }
    # 联系方式（模板按字段是否存在渲染）
    for key in ("email", "phone", "website", "github", "linkedin"):
        if contacts.get(key):
            sidebar[key] = contacts[key]

    languages = rsuf.get("languages") or []
    if languages:
        sidebar["languages"] = {
            "title": "语言",
            "info": [{"idiom": l.get("name", ""), "level": l.get("level", "")} for l in languages],
        }

    data = {"sidebar": sidebar}

    if basic.get("summary"):
        data["career-profile"] = {"title": "个人简介", "summary": basic["summary"]}

    edu = rsuf.get("education") or []
    if edu:
        data["education"] = {
            "title": "教育经历",
            "info": [{
                "degree": e.get("degree", ""),
                "university": e.get("school", ""),
                "time": _time_range(e.get("start"), e.get("end")),
                "details": e.get("details", ""),
            } for e in edu],
        }

    exp = rsuf.get("experience") or []
    if exp:
        data["experiences"] = {
            "title": "工作经历",
            "info": [{
                "role": e.get("role", ""),
                "company": e.get("company", ""),
                "time": _time_range(e.get("start"), e.get("end")),
                "details": e.get("details", ""),
            } for e in exp],
        }

    certs = rsuf.get("certifications") or []
    if certs:
        data["certifications"] = {
            "title": "证书与荣誉",
            "list": [_prune({
                "name": c.get("name", ""),
                "start": c.get("date", ""),
                "organization": c.get("org", ""),
                "details": c.get("details", ""),
            }) for c in certs],
        }

    projects = rsuf.get("projects") or []
    if projects:
        data["projects"] = {
            "title": "项目经历",
            "assignments": [_prune({
                "title": p.get("name", ""),
                "tagline": p.get("tagline", ""),
                "link": p.get("link", ""),
            }) for p in projects],
        }

    skills = rsuf.get("skills") or []
    if skills:
        data["skills"] = {
            "title": "专业技能",
            "toolset": [{"name": s.get("name", ""), "level": f"{s.get('level', 75)}%"} for s in skills],
        }

    # CC-BY 3.0 署名（Orbit 模板要求保留）
    data["footer"] = (
        'Designed with <i class="fas fa-heart"></i> by '
        '<a href="http://themes.3rdwavemedia.com" target="_blank">Xiaoying Riley</a> '
        'for developers · Published with 简历海'
    )
    return data


# 适配器注册表：新增模板时在此登记
ADAPTERS = {
    "online-cv": to_online_cv,
}


def adapt(rsuf, template, skin="blue"):
    if template not in ADAPTERS:
        raise ValueError(f"未知模板: {template}（可用: {', '.join(ADAPTERS)}）")
    return ADAPTERS[template](rsuf, skin=skin)
