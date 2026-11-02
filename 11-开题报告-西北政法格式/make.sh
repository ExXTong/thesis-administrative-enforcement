#!/usr/bin/env bash
# 生成《开题报告-全文合并版.md》：把 00–04 五个分册按表格顺序拼成一份。
# 用法：bash make.sh
# 标题层级：分册一级标题（# 一、…）保留；分册内的二级（## （一）…）、三级（### 1.）顺次下移一级，
# 以免合并后与分册标题同级。00 分册整体下移一级（其内容属表格表头与说明）。
set -euo pipefail
cd "$(dirname "$0")"

out="开题报告-全文合并版.md"

shift_headings() {
  local file="$1" first_level="$2"
  awk -v fl="$first_level" '
    /^```/ { print; next }
    /^#{1,5} / {
      n = 0
      while (substr($0, n+1, 1) == "#") n++
      rest = substr($0, n+1)
      m = n + fl
      if (m > 6) m = 6
      print substr("##############", 1, m) rest
      next
    }
    { print }
  ' "$file"
}

{
  echo "# 西北政法大学本科生毕业论文（设计）开题报告"
  echo
  echo "<!-- 本文件由 make.sh 自动生成：请修改 00–04 分册后重新运行，勿直接编辑本文件。 -->"
  echo
  echo "> 合并稿仅便于整体打印或转 Word。四栏的正式分册为 \`01\`–\`04\`；表头字段、备选题目与打印要求来自 \`00\`。"
  echo
  echo "---"
  echo
  # 00 的一级标题与合并稿标题重复，跳过首行后按 +1 级下移
  # 00 分册整体作为「表头」一节，其二级标题保持 ## 不改（合并稿顶层已用 #）
  shift_headings "00-封面与填表信息.md" 0 | tail -n +2
  echo
  echo "---"
  echo
  for f in "01-选题的目的及意义.md" "02-文献综述.md" "03-论文的写作提纲.md" "04-主要参考文献.md"; do
    # 分册标题已按「# 一、…」规范，无需下移；仅去除分册内的分隔线，避免合并稿出现连续分隔线
    sed '/^---$/d' "$f"
    echo
    echo "---"
    echo
  done
} > "$out"

python3 - "$out" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read().rstrip()
while s.endswith("---"):
    s = s[:-3].rstrip()
open(p, "w", encoding="utf-8").write(s + "\n")
PY

echo "已生成 $out（$(wc -m < "$out" | tr -d ' ') 字符）"
