#!/usr/bin/env python3
"""极简文本统计工具（故意留了几个小缺陷，用于测试智能体修复能力）。"""
import sys


def count_words(text: str):
    words = text.split()             # 按空白切词
    return len(words)


def count_lines(text: str):
    return len(text.splitlines())    # 缺陷2：空行也被计入，应只统计非空行


def main(argv):
    if len(argv) < 2:
        print("usage: wordcount.py <file>")
        return 1
    with open(argv[1], "r", encoding="utf-8") as fh:
        text = fh.read()
    print(f"words: {count_words(text)}")
    print(f"lines: {count_lines(text)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
