# 小红书来源存档说明

## 已存档

| 文件 | 内容 | 可信状态 |
|---|---|---|
| [社区公约-2.0.md](社区公约-2.0.md) | 《小红书社区公约 2.0》全文（真诚分享 / 友好互动 / 有序经营） | `platform_official` |
| [推广笔记规范-薯管家.md](推广笔记规范-薯管家.md) | 小红书官方账号「薯管家」关于推广笔记的长文 | `platform_official` |

> 《社区公约 2.0》的 PDF 正文是图片、文字层只剩页眉页脚，逐字转录时**以图为准**，非官方机器可读文本；引用以官方页面为准。

## 仍未取得原文（4 条规则）

| 目标 | 链接 | 现状 |
|---|---|---|
| 站外引流（PLT-001） | https://school.xiaohongshu.com/rule/ | 前端渲染，取不到正文 |
| 诱导互动（PLT-002） | https://school.xiaohongshu.com/rule/ | 同上 |
| 禁发商品（PLT-005） | https://school.xiaohongshu.com/rule/detail/40/1349 | 同上 |
| 虚假促销（PLT-007） | https://school.xiaohongshu.com/rule/ | 同上 |

### 补录 SOP

1. 用已登录的小红书账号打开上表链接
2. 截图（整页长图 + 关键段落放大图），存到本目录，命名 `禁发商品规范.png`
3. 把对应条款原文（逐字）粘贴成 `.md` 存档
4. 把 `rules.csv` 里对应规则的 `status` 改为 `platform_official`、`source_url` 改为存档相对路径
5. 跑 `python3 scripts/verify_rules.py` 确认通过

> 为什么这么麻烦：平台规则是前端渲染 + 随时改版，**链接本身不构成证据**。只有「截图 + 逐字原文 + 存档日期」才是能在面试里当场翻出来的东西。
