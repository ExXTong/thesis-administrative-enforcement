#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把仓库根目录新放入的 PDF 转成可检索文字版，归档到 `OCR/`。

用法（在仓库根目录执行）：

    python3 OCR/scripts/pdf2text_ocr.py

处理规则与 `09-文献清单/全文文本/scripts/pdf2text.py` 完全一致（本脚本直接
复用该模块）：优先取 PDF 内嵌文字层；整页扫描件、只剩页眉页码的扫描正文、
字体编码损坏的页面才送 RapidOCR，且只有 OCR 结果明显更长时才采用；空白页
只留页标记；规范化只做机械处理，不改写、不翻译、不纠错。

本脚本只读根目录的 `*.pdf`，输出 `OCR/*.md` 与 `OCR/_manifest.csv`，不移动、
不修改任何原件。新增 PDF 后重跑即可。
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 仓库根目录
OUT = ROOT / "OCR"
P2T_PATH = ROOT / "09-文献清单" / "全文文本" / "scripts" / "pdf2text.py"

# 五份没有正文标题可用的上传件，标题由内容人工核读后补上；其余按文件名。
TITLES = {
    "PDF_612498404.pdf": "2027年全国硕士研究生招生考试网上报名信息（学信网）",
    "blank.pdf": "台陆行政法选题评估与路径优化（Gemini 对话导出）",
    "ntu-108-1.pdf": "論行政法上義務之概括繼受（邱稚宸，臺灣大學法律學研究所碩士論文，2017）",
    "9xD7rCBP.pdf": "論公法上金錢給付義務之行政執行標的（郭芳秀，國立政治大學法律學系碩士論文，指導教授詹鎮榮，2020 年 7 月）",
    "76_Zwang_Geld.pdf": "公法上金錢給付義務之執行（程明修《行政法》講義 Nr. 76）",
    "赵德关｜构建我国对物行政处罚制度初探_违法_行政处罚法_建设.pdf": "构建我国对物行政处罚制度初探（赵德关，《法治政府建设》2025 年第 4 期）",
}

NOTES = {
    "PDF_612498404.pdf": "含身份证号、手机号、家庭与学籍信息，属个人材料，勿外传",
    "blank.pdf": "文件名与内容不符：正文是 Gemini 对话导出《台陆行政法选题评估与路径优化》",
    "9xD7rCBP.pdf": "文件名为下载乱码名；原件即政大碩士論文（DOI 10.6814/NCCU202001394，178 页），入库副本为 `09-文献清单/中文文献PDF/論公法上金錢給付義務之行政執行標的_郭芳秀.pdf`",
    "76_Zwang_Geld.pdf": "2 页讲义流程图，梳理台湾公法上金钱给付义务的执行流程（告戒、移送行政執行處、執行處措施、限制住居与管收）；缺藏台账外的补充上传件，不入 `中文文献PDF/`",
    "赵德关｜构建我国对物行政处罚制度初探_违法_行政处罚法_建设.pdf": "文件名取自网页标题；原件为网页转储（含站点导航文字），正文转自《法治政府建设》2025 年第 4 期，非期刊排版；入库副本为 `09-文献清单/中文文献PDF/构建我国对物行政处罚制度初探_赵德关.pdf`",
    "ntu-108-1.pdf": "原件为 AES 加密（仅限制复制/打印权限），文字层仍可直接抽取，无需解密",
}


def load_pdf2text():
    spec = importlib.util.spec_from_file_location("pdf2text", P2T_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"找不到共用的转换脚本：{P2T_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archived_body(md_path: Path) -> str | None:
    """已有 `全文文本/中文文献/` 文字版的正文（去掉头部信息）。"""
    if not md_path.is_file():
        return None
    text = md_path.read_text(encoding="utf-8")
    marker = text.find("--- 第 1 页")
    return text[marker:].strip() if marker != -1 else text.strip()


def front_matter(path: Path, info: dict, today: str, digest: str, note: str) -> str:
    title = TITLES.get(path.name, path.stem)
    lines = [
        f"# {title}",
        "",
        f"- 原件：`{path.name}`",
        f"- 原件 SHA-256：`{digest}`",
    ]
    if info["pages"] is not None:
        lines.append(f"- 页数：{info['pages']}")
    lines.append(f"- 字数：{info['chars']}")
    lines.append(f"- 文字来源：{info['method']}")
    if info["ocr_pages"]:
        pages = "、".join(str(p) for p in info["ocr_pages"])
        lines.append(f"- OCR 页：第 {pages} 页")
    if info["blank_pages"]:
        pages = "、".join(str(p) for p in info["blank_pages"])
        lines.append(f"- 空白页（原件即无内容）：第 {pages} 页")
    if info["pdf_title"] and info["pdf_title"] != path.stem:
        lines.append(f"- 原件元数据标题：{info['pdf_title']}")
    if note:
        lines.append(f"- 备注：{note}")
    lines.append(f"- 生成：`OCR/scripts/pdf2text_ocr.py`，{today}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    today = dt.date.today().isoformat()
    p2t = load_pdf2text()
    pdfs = sorted(ROOT.glob("*.pdf"))
    if not pdfs:
        print("根目录没有 PDF，未生成任何文件。", file=sys.stderr)
        return 1

    rows = []
    failures = []
    for path in pdfs:
        digest = sha256(path)
        note = NOTES.get(path.name, "")
        duplicate_of = ROOT / "09-文献清单" / "中文文献PDF" / path.name
        check = "新增"
        if duplicate_of.is_file() and sha256(duplicate_of) == digest:
            note = (note + "；" if note else "") + "与 `09-文献清单/中文文献PDF/` 同名文件字节相同"

        try:
            body, info = p2t.pdf_to_markdown(path)
        except Exception as exc:  # 原件损坏或不是 PDF 时如实记录，不做猜测性补写
            error = f"{type(exc).__name__}: {exc}"
            print(f"[失败] {path.name}: {error}", file=sys.stderr)
            failures.append(path.name)
            rows.append(
                {
                    "原件": path.name,
                    "输出": "",
                    "页数": "",
                    "字数": "",
                    "文字来源": "转换失败",
                    "校验": "失败",
                    "备注": (note + "；" if note else "") + error,
                }
            )
            continue

        out_path = OUT / f"{path.stem}.md"
        out_path.write_text(front_matter(path, info, today, digest, note) + body + "\n", encoding="utf-8")

        if duplicate_of.is_file() and sha256(duplicate_of) == digest:
            old = archived_body(ROOT / "09-文献清单" / "全文文本" / "中文文献" / out_path.name)
            check = "与全文文本一致" if old is not None and old == body.strip() else "与全文文本不一致"
            if check != "与全文文本一致":
                failures.append(path.name)

        # 页标记数必须等于页数；正文长度必须等于头部所记字数
        markers = body.count("--- 第 ")
        if markers != info["pages"] or len(body) != info["chars"]:
            check = "校验失败"
            failures.append(path.name)

        rows.append(
            {
                "原件": path.name,
                "输出": out_path.relative_to(ROOT).as_posix(),
                "页数": info["pages"],
                "字数": info["chars"],
                "文字来源": info["method"],
                "校验": check,
                "备注": note,
            }
        )
        print(f"[完成] {path.name} -> {out_path.name}（{info['pages']} 页 / {info['chars']} 字 / {info['method']}）")

    manifest = OUT / "_manifest.csv"
    # 与仓库既有 CSV 一致：UTF-8 带 BOM，Excel 直接可读
    with manifest.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["原件", "输出", "页数", "字数", "文字来源", "校验", "备注"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"[完成] 清单 -> {manifest.relative_to(ROOT)}（{len(rows)} 条）")
    if failures:
        print(f"[失败] {len(failures)} 条未通过：{'、'.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
