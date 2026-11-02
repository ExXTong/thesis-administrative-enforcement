#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `09-文献清单/` 下的文献原件转成 Markdown 全文。

用法（在仓库根目录执行）：

    python3 09-文献清单/全文文本/scripts/pdf2text.py

处理规则：

1. PDF 优先取内嵌文本层（`get_text(sort=True)`，保留页眉与阅读顺序）；只有
   下列三种页送 OCR（RapidOCR），且仅当 OCR 结果明显长于原有文字时才采用：
   整页扫描件（文字层 < 400 字符、图像覆盖 ≥ 0.3）；文字层几乎为空、但有墨迹
   和局部图像（正文是扫描图，文字层只剩页眉页码）；文字层字体编码损坏（私用区
   字符成片，超过 20 个且占比 > 5%，例如个别 CNKI 学位论文封面）。
2. 渲染墨迹比例 < 0.001 且文字层几乎为空，判为空白页，不送 OCR，只留页标记。
3. HTML 网页文章取 `<article>` 正文，按块级元素转成段落。
4. 每个文档在文件头部写一段元信息（原件路径、页数、文字来源、OCR 页），
   正文用 `--- 第 N 页 ---` 分隔，OCR 页标记为 `--- 第 N 页（OCR）---`。
5. 规范化只做机械处理：去掉控制字符、私用区字符（换成「•」）、压缩空行；
   不含汉字的英文/数字行若是全角字形，则折成半角（部分 CNKI 原件把英文摘要
   整段输出为全角字形）。含汉字的行一律不动，中文标点保持全角。
6. 输出镜像到 `09-文献清单/全文文本/{中文文献,外文文献,原始法条}/`，
   并生成 `_manifest.csv`。
7. 个别原件本身损坏或不是 PDF（下载时拿到的是反爬验证页），不能就地修改，
   于是把可用副本放在 `全文文本/_来源补件/` 下作为替身来源，并在清单里注明；
   `原样转换失败` 的条目不做任何猜测性补写。

依赖：pymupdf；扫描页 OCR 另需 rapidocr-onnxruntime；HTML 需 beautifulsoup4。
不修改、不移动任何原件。
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[3]  # 仓库根目录
LIT = ROOT / "09-文献清单"
OUT = LIT / "全文文本"

# (源目录, 输出子目录, 类别名)
SOURCES = [
    (LIT / "中文文献PDF", OUT / "中文文献", "中文文献"),
    (LIT / "外文文献PDF", OUT / "外文文献", "外文文献"),
    (LIT / "外文文献PDF" / "primary-sources", OUT / "原始法条", "原始法条"),
]

MIN_TEXT_CHARS = 60        # 文字层几乎为空的阈值
PAGE_HEADER_CHARS = 400    # 文字层只剩页眉页码时的上限
MIN_IMAGE_COVER = 0.30     # "整页扫描件"的页面图像覆盖率
BLANK_INK = 0.001          # 墨迹比例低于此值视为空白页
OCR_DPI = 300

_ocr_engine = None


def ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def page_ink(page) -> float:
    """渲染成灰度图后，暗像素（<200）占比。"""
    pix = page.get_pixmap(dpi=40, colorspace=pymupdf.csGRAY, alpha=False)
    samples = pix.samples
    if not samples:
        return 0.0
    return sum(1 for v in samples if v < 200) / len(samples)


def image_cover(page) -> float:
    """页面内最大图像占页面面积的比例。"""
    area = page.rect.width * page.rect.height
    if not area:
        return 0.0
    best = 0.0
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        best = max(best, (x1 - x0) * (y1 - y0) / area)
    return best


def ocr_page(page) -> str:
    pix = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY, alpha=False)
    result, _ = ocr_engine()(pix.tobytes("png"))
    if not result:
        return ""
    return "\n".join(line[1] for line in result)


def latin_ratio(text: str) -> float:
    """拉丁字母在全部字母中的占比（标点、数字不计入）。"""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    latin = [c for c in letters if "a" <= c.lower() <= "z"]
    return len(latin) / len(letters)


def to_halfwidth_ascii(text: str) -> str:
    """全角字母、数字、ASCII 符号折成半角（只用于不含汉字的英文行）。"""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:  # 全角空格，夹在英文行里统一成半角空格
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def fullwidth_alnum_ratio(text: str) -> float:
    """全角英文字母/数字在全部字母中的占比。"""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    fw = [c for c in letters if 0xFF21 <= ord(c) <= 0xFF3A or 0xFF41 <= ord(c) <= 0xFF5A]
    return len(fw) / len(letters)


def should_fold_ascii(line: str) -> bool:
    """判断一行是否属于「整行都是英文/数字，只是字形是全角」。

    含汉字的行一律不动（中文正文的标点保持全角）；只折纯英文数字行与几乎全角
    的英文行，例如部分 CNKI 原件把英文摘要整段输出成全角字形。
    """
    if any("\u4e00" <= c <= "\u9fff" for c in line):
        return False
    return latin_ratio(line) > 0.5 or fullwidth_alnum_ratio(line) > 0.5


PUA_RE = re.compile(r"[\ue000-\uf8ff]")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize(text: str) -> str:
    text = CTRL_RE.sub("", text)
    # 私用区字符常被 PDF 用来藏项目符号（如 Symbol 字体），换成普通圆点
    text = PUA_RE.sub("•", text)
    lines = []
    for line in text.split("\n"):
        line = line.rstrip()
        stripped = line.strip()
        if stripped and should_fold_ascii(stripped):
            line = to_halfwidth_ascii(line)
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_to_markdown(path: Path) -> tuple[str, dict]:
    head = path.open("rb").read(512).lstrip()
    if head[:1] in (b"<",) or b"<html" in head[:512].lower() or b"<!doctype" in head[:512].lower():
        raise RuntimeError("文件不是 PDF，而是网页（下载时拿到的是反爬验证页）")

    doc = pymupdf.open(path)
    if doc.page_count == 0:
        raise RuntimeError("无法打开 PDF（页数为 0，缺少 xref/trailer）")

    parts: list[str] = []
    ocr_pages: list[int] = []
    blank_pages: list[int] = []

    for i in range(doc.page_count):
        page = doc[i]
        text = page.get_text(sort=True).strip()
        ink = page_ink(page)
        cover = image_cover(page)
        is_ocr = False
        is_blank = False

        # 三种情形才 OCR：整页扫描件（几乎无文字、图像铺满）；正文其实是扫描
        # 图像、文字层只剩页眉页码；或文字层字体编码损坏（私用区字符成片，如
        # 个别 CNKI 学位论文封面）。零星几个私用区字符只是 Symbol 项目符号，
        # 正文本身没问题，不该送 OCR。
        pua = sum(1 for ch in text if PUA_RE.match(ch))
        garbled = pua > 20 and pua / max(len(text), 1) > 0.05
        needs_ocr = (
            (len(text) < PAGE_HEADER_CHARS and cover >= MIN_IMAGE_COVER and ink > BLANK_INK)
            or (len(text) < MIN_TEXT_CHARS and ink > 0.01 and cover > 0.10)
            or garbled
        )

        if ink < BLANK_INK and len(text) < MIN_TEXT_CHARS:
            is_blank = True
            text = ""
        elif needs_ocr:
            ocr_text = ocr_page(page).strip()
            # 文字层乱码时，OCR 字数少也可能更干净，放宽到原有字数的四成
            threshold = len(text) * (0.4 if garbled else 1.2)
            if len(ocr_text) > threshold:
                text = ocr_text
                is_ocr = True
            if len(text) < MIN_TEXT_CHARS and ink < BLANK_INK * 4:
                is_blank = True
                text = ""

        if is_blank:
            blank_pages.append(i + 1)
            marker = f"--- 第 {i + 1} 页（空白页） ---"
        elif is_ocr:
            ocr_pages.append(i + 1)
            marker = f"--- 第 {i + 1} 页（OCR） ---"
        else:
            marker = f"--- 第 {i + 1} 页 ---"

        parts.append(f"{marker}\n\n{text}" if text else marker)

    meta_title = (doc.metadata or {}).get("title") or ""
    doc.close()

    body = normalize("\n\n".join(parts))
    info = {
        "pages": len(parts),
        "chars": len(body),  # 与写出的正文长度一致，含页标记
        "ocr_pages": ocr_pages,
        "blank_pages": blank_pages,
        "pdf_title": meta_title.strip(),
        "method": "内嵌文本层" + ("＋OCR" if ocr_pages else ""),
    }
    return body, info


def html_to_markdown(path: Path) -> tuple[str, dict]:
    from bs4 import BeautifulSoup

    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
        tag.decompose()
    article = soup.find("article") or soup.find("main") or soup.body or soup

    blocks: list[str] = []
    for el in article.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
        if el.find(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
            continue  # 只取叶子块，避免重复
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name == "h1":
            blocks.append(f"# {text}")
        elif el.name == "h2":
            blocks.append(f"## {text}")
        elif el.name in ("h3", "h4"):
            blocks.append(f"### {text}")
        elif el.name == "li":
            blocks.append(f"- {text}")
        elif el.name == "blockquote":
            blocks.append(f"> {text}")
        else:
            blocks.append(text)

    body = normalize("\n\n".join(blocks))
    title = soup.title.get_text(strip=True) if soup.title else path.stem
    info = {
        "pages": None,
        "chars": len(body),
        "ocr_pages": [],
        "blank_pages": [],
        "pdf_title": title,
        "method": "网页正文（article）",
    }
    return body, info


def front_matter(path: Path, info: dict, today: str) -> str:
    rel = path.relative_to(ROOT).as_posix()
    lines = [
        f"# {path.stem}",
        "",
        f"- 原件：`{rel}`",
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
    lines.append(f"- 生成：`09-文献清单/全文文本/scripts/pdf2text.py`，{today}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    today = dt.date.today().isoformat()
    stand_in_dir = OUT / "_来源补件"
    rows = []
    for src_dir, out_dir, category in SOURCES:
        if not src_dir.is_dir():
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(src_dir.iterdir()):
            suffix = path.suffix.lower()
            if suffix not in (".pdf", ".html", ".htm"):
                continue
            source_path = path
            used_stand_in = False
            error = None
            body = info = None
            try:
                if suffix == ".pdf":
                    body, info = pdf_to_markdown(path)
                else:
                    body, info = html_to_markdown(path)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                # 原件损坏时，允许用 _来源补件/ 下的同名可用副本代替
                stand_in = stand_in_dir / path.name
                if stand_in.is_file():
                    try:
                        body, info = pdf_to_markdown(stand_in)
                        source_path = stand_in
                        used_stand_in = True
                        error = None
                    except Exception as exc2:
                        error = f"{error}；补件亦失败：{type(exc2).__name__}: {exc2}"

            if body is None:
                print(f"[失败] {path.name}: {error}", file=sys.stderr)
                rows.append(
                    {
                        "类别": category,
                        "原件": path.relative_to(ROOT).as_posix(),
                        "输出": "",
                        "页数": "",
                        "字数": "",
                        "文字来源": "转换失败",
                        "备注": error or "",
                    }
                )
                continue

            out_path = out_dir / f"{path.stem}.md"
            head = front_matter(path, info, today)
            if used_stand_in:
                rel = source_path.relative_to(ROOT).as_posix()
                head = head.replace(
                    "---\n\n",
                    f"- 原件不可用：该文件已损坏（无 xref/页数），不能就地转换\n"
                    f"- 实际转换所用副本：`{rel}`（同名，自 gesetze-im-internet.de 重新下载）\n\n---\n\n",
                )
            out_path.write_text(head + body + "\n", encoding="utf-8")
            note = ""
            if info["ocr_pages"]:
                note = f"OCR {len(info['ocr_pages'])} 页"
            if info["blank_pages"]:
                note = (note + "；" if note else "") + f"空白页 {len(info['blank_pages'])}"
            if used_stand_in:
                note = (note + "；" if note else "") + "原件损坏，用 _来源补件 副本转换"
            rows.append(
                {
                    "类别": category,
                    "原件": path.relative_to(ROOT).as_posix(),
                    "输出": out_path.relative_to(ROOT).as_posix(),
                    "页数": info["pages"] if info["pages"] is not None else "",
                    "字数": info["chars"],
                    "文字来源": info["method"],
                    "备注": note,
                }
            )
            print(f"[完成] {path.name} -> {out_path.name} ({info['chars']} 字)")

    manifest = OUT / "_manifest.csv"
    # 与本仓库既有 CSV（10-法宝全量检索/汇总/）一致：UTF-8 带 BOM，Excel 直接可读
    with manifest.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["类别", "原件", "输出", "页数", "字数", "文字来源", "备注"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[完成] 清单 -> {manifest.relative_to(ROOT)}（{len(rows)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
