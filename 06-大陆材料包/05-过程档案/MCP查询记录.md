# 北大法宝 MCP 查询记录（可复现）

> 时间：2026-09-26 16:29–16:45｜执行者：对话主智能体（本机 DSH）
> 服务状态：14 个服务全部已开启（检索司法案例-关键词 25 分/次；检索法律法规-关键词 25 分/次；精准查找法条-关键词 25 分/次；检索法律法规-语义 125 分/次；法规与法条沿革 75 分/次；检索司法案例-语义 125 分/次 等）

| # | 工具 | 参数 | 结果 |
|---|---|---|---|
| 1 | `pkulaw_account.list_entitlements` | onlyTurnedOn=true | 14/14 已开启 |
| 2 | `pkulaw_law.get_law_list` | title="人民法院办理执行案件规范" | 2 版（2017／第二版） |
| 3 | `pkulaw_case.get_case_list` | caseClassName="非诉行政行为申请执行审查", fulltext="放弃继承" | **Total 24**（本页 20；原始返回存 `04-原始MCP返回/`） |
| 4 | `pkulaw_case.get_case_list` | caseClassName="非诉行政行为申请执行审查", fulltext="遗产管理人" | **Total 2**：(2023)渝0109行审83号、(2026)川0302行审45号 |
| 5 | `pkulaw_fatiao.get_law_item_content` | title="人民法院办理执行案件规范", tiao_num=59 | 第二版 §59＝被执行人死亡、宣告失踪 |
| 6 | `pkulaw_fatiao.get_law_item_content` | title="人民法院办理执行案件规范", tiao_num=66 | 第二版 §66＝股东出资不足 |
| 7 | `pkulaw_law_search.search_article` | text="违反治安管理行为人死亡，不予行政处罚，终止调查" | 公安令160号 §259；《公安派出所正规化建设规范》§87；及各历史版本 |
| 8 | `pkulaw_law_search.search_article` | text="纳税人死亡后，欠缴税款由继承人、遗产管理人在遗产范围内缴纳" | 民法典 §1161；民诉法解释 §473；国税函〔2002〕803号；继承法§33（已废止） |
| 9 | `pkulaw_law_search.search_article` | text="参保人员死亡，个人账户余额可以继承；追回多享受社会保险待遇" | 江苏／成都／鄂尔多斯／交通部／广州（多为地方规范性文件） |
| 10 | `pkulaw_law.get_law_list` | title="关于追回多享受社会保险待遇工作的通知" | **0 结果**（人社部发〔2024〕74号 法宝未收录） |
| 11 | `pkulaw_law.get_law_list` | title="中华人民共和国治安管理处罚法" | 13 件；**2025修订（主席令第49号）2026-01-01 施行，现行有效** |
| 12 | `pkulaw_law.get_law_list` | title="核销", fulltext="死欠" | 8 件，**全部企业语境** |
| 13 | `pkulaw_law_search.search_article` | text="追回多享受社会保险待遇，向不当得利受益人追收" | 广州两件（已废止）；**山西七部门〔2023〕87号（现行有效）** |
| 14 | `pkulaw_law_search.search_article` | text="追加未缴纳出资的股东为被执行人" | 法释2020-21 §17；执行规范第二版 §66；法释2016-21 §17；**执行规范2017 §59**（条号对应锁定） |

## 未闭合／限制
1. 法宝网页端反爬：`web_fetch` 对 pkulaw.com 案例页返回 HTTP 200 但**正文为空** → **无法抓取网页版原文**，本包内容全部取自 MCP 返回文本；
2. 法宝 MCP **无"引证追溯／被引用情况"接口** → 16号 的引用统计为案例库全文还原，**下限口径**；
3. 法宝 MCP **无期刊库** → 撞题文献（陈思融之后是否有第二篇）需外部通道；
4. 台湾側法规／裁判库未测。
