#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把带「权限口令」的 PDF 解密成无加密副本，并逐页核对内容未变。

适用情形：PDF 用了标准安全处理器（Standard security handler），
**用户口令为空**、只设了所有者口令（owner password），因此任何阅读器都能打开、
也能直接复制文字，但文件里带着 `/Encrypt` 字典、权限位禁止提取文字。
典型来源是学校论文系统（台大 TDR 等）与水印导出功能。
这不是「忘记密码」的那种文件——它是**用空用户口令加密**，所以不需要猜口令。

用法（在仓库根目录执行）：

    python3 09-文献清单/全文文本/scripts/decrypt_pdf.py 输入.pdf 输出.pdf
    python3 09-文献清单/全文文本/scripts/decrypt_pdf.py 输入.pdf 输出.pdf --overwrite

处理规则：

1. 打开后先报告加密参数（算法、R、P 权限位、是否空用户口令）。若 `needs_pass`
   非零（即真的需要口令才能打开），**直接报错退出**，不做任何猜测或暴力尝试。
2. 用 `save(encryption=PDF_ENCRYPT_NONE)` 重写文件；对象流重新生成、字体与
   图片流按原字节保留（`deflate` 只压缩未压缩流），不重新栅格化页面。
3. 写完后重新打开输出，逐页核对：页数、每页文字（`get_text()` 全等）、每页 48dpi
   渲染像素的 SHA-256 全等；任何一页不一致就删掉输出并以非零退出码结束。
4. 不改动、不删除输入文件。输出文件已存在时默认拒绝写入，须显式 `--overwrite`。

依赖：pymupdf（与 `pdf2text.py` 相同，仓库已有依赖，不引入新包）。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pymupdf


def describe_encryption(doc) -> dict:
    """从元数据与权限位读出可读的加密描述。"""
    meta = doc.metadata or {}
    perms = doc.permissions
    return {
        "加密描述": meta.get("encryption") or "（元数据未标注）",
        "权限位": perms,
        "需口令才能打开": doc.needs_pass,
        "可提取文字": bool(perms & pymupdf.PDF_PERM_COPY),
        "可打印": bool(perms & pymupdf.PDF_PERM_PRINT),
        "可修改": bool(perms & pymupdf.PDF_PERM_MODIFY),
    }


def page_fingerprint(doc, dpi: int = 48) -> list[tuple[str, str]]:
    """每页（文字 SHA-256, 渲染像素 SHA-256）。"""
    out = []
    for page in doc:
        text = hashlib.sha256(page.get_text().encode("utf-8")).hexdigest()
        pix = page.get_pixmap(dpi=dpi)
        pixels = hashlib.sha256(pix.samples).hexdigest()
        out.append((text, pixels))
    return out


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    if not args:
        print(
            "用法：python3 09-文献清单/全文文本/scripts/decrypt_pdf.py "
            "输入.pdf 输出.pdf [--overwrite]",
            file=sys.stderr,
        )
        return 2
    if len(args) != 2:
        print("错误：需要恰好两个位置参数：输入.pdf 输出.pdf", file=sys.stderr)
        return 2

    src, dst = Path(args[0]), Path(args[1])
    if not src.is_file():
        print(f"错误：输入文件不存在：{src}", file=sys.stderr)
        return 2
    if src.resolve() == dst.resolve():
        print("错误：输出不能覆盖输入（本脚本不改原件）", file=sys.stderr)
        return 2
    if dst.exists() and "--overwrite" not in flags:
        print(f"错误：输出文件已存在，如需重写请加 --overwrite：{dst}", file=sys.stderr)
        return 2

    doc = pymupdf.open(src)
    if doc.page_count == 0:
        print(f"错误：无法打开 PDF（页数为 0，文件可能损坏）：{src}", file=sys.stderr)
        return 1

    print(f"输入：{src}（{src.stat().st_size} 字节，{doc.page_count} 页）")
    for key, value in describe_encryption(doc).items():
        print(f"  {key}：{value}")

    if doc.needs_pass:
        print(
            "错误：该 PDF 需要口令才能打开（用户口令非空），本脚本不猜口令。\n"
            "      请向权利人索取口令，或改用其他合法途径取得文件。",
            file=sys.stderr,
        )
        return 1

    before = page_fingerprint(doc)
    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(
        dst,
        encryption=pymupdf.PDF_ENCRYPT_NONE,
        garbage=4,
        deflate=True,
        use_objstms=1,
    )
    doc.close()

    dec = pymupdf.open(dst)
    print(f"输出：{dst}（{dst.stat().st_size} 字节，{dec.page_count} 页）")
    for key, value in describe_encryption(dec).items():
        print(f"  {key}：{value}")

    after = page_fingerprint(dec)
    problems = []
    if len(before) != len(after):
        problems.append(f"页数不一致：{len(before)} → {len(after)}")
    text_diff = [i + 1 for i, (a, b) in enumerate(zip(before, after)) if a[0] != b[0]]
    pixel_diff = [i + 1 for i, (a, b) in enumerate(zip(before, after)) if a[1] != b[1]]
    if text_diff:
        problems.append(f"文字不一致的页：{text_diff[:20]}")
    if pixel_diff:
        problems.append(f"渲染不一致的页：{pixel_diff[:20]}")

    if problems:
        print("核对失败，输出文件不保留：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        dst.unlink(missing_ok=True)
        return 1

    print(f"核对通过：{len(after)} 页文字与 48dpi 渲染像素均与原件一致，输出已无加密。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
