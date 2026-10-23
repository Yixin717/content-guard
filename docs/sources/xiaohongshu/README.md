# 小红书来源存档说明

## 已存档

| 文件 | 内容 | 可信状态 |
|---|---|---|
| [推广笔记规范-薯管家.md](推广笔记规范-薯管家.md) | 小红书官方账号「薯管家」关于推广笔记的长文（全文） | `platform_official` —— 官方账号内容，非规则中心正式条款 |

## 待补（抓取受阻）

| 目标 | 链接 | 尝试结果 |
|---|---|---|
| 《小红书社区公约》 | https://fe.xiaohongshu.com/ditto/vincent/e13cbe5b6a5e4f7794971b4597ab35bd | 2026-10-23 抓取：HTTP 200，但返回 124 KB 的 SPA 外壳，正文由前端 JS 渲染，仅能取到标题「小红书社区公约」。**无法机器取证。** |
| 小红书规则中心（商家/社区/推广） | https://school.xiaohongshu.com/rule/ | 同上，前端渲染，返回空壳。 |
| 「虚假宣传：功效虚假」实施细则 | https://school.xiaohongshu.com/rule/detail/106/119728 | 同上。 |
| 「虚假宣传：广告禁用词」实施细则 | https://school.xiaohongshu.com/rule/detail/115/2737 | 同上。 |
| 《禁发商品及信息管理规范》 | https://school.xiaohongshu.com/rule/detail/40/1349 | 同上。 |

### 补录 SOP（约 10 分钟）

1. 用已登录的小红书账号打开上表任一链接
2. 截图：整页长图 1 张 + 关键段落放大图 1 张，存到 `docs/sources/xiaohongshu/` 下，命名 `社区公约-第X条.png`
3. 把对应条款原文（逐字）粘贴进本目录的 `.md` 存档
4. 把 `rules.csv` 里对应规则的 `status` 从 `platform_pending` 改为 `platform_official`，`source_url` 改为存档文件的相对路径
5. 跑 `python3 scripts/verify_rules.py` 确认通过

> 为什么这么麻烦：平台规则是前端渲染 + 会随时改版，链接本身不构成证据。**截图 + 逐字原文 + 抓取日期**才是能在面试里当场翻出来的东西。
