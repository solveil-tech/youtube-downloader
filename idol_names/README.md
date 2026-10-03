# 女团成员姓名别名数据库

最近增量核对日期：2026-10-03（Baby DONT Cry；其余资料保留原快照）。已接入下载器源码与 EXE 的组合/成员/日期搜索。

新增 Baby DONT Cry 四名成员的英韩艺名、本名与格式变体，另在曲目库补充八首已核实歌曲。官方艺名依据 P NATION，本名依据 KProfiles，来源与生成候选分别标记。下载器右上角数据库按钮可从 GitHub 更新或导入本地 JSON，之后仅更新数据无需再次打包 EXE。

已补充 `ifeye / 이프아이` 六名成员及英文、韩文姓名别名，并纳入最新 EXE。艺名参考 Genie 艺人页，韩文本名参考 KProfiles；生成的音译候选仍与来源确认写法分开标记。可用项目的 `check_ytdl.bat` 测试源码。

配置中新增组合后，可使用 `python idol_names/build_database.py --add-group ifeye` 增量补充，保留其他组合的原始资料快照。

## 如何查看

双击 `姓名别名表.html`，用浏览器离线查看。支持按已收录的中文、英文、韩文或团体搜索，按团体筛选，以及只查看同名冲突。新增中文显示名和依据列；未补充的成员显示待核对。每个来源别名都可点击核对资料，生成候选用黄色区分。页面没有外部脚本或联网依赖。

## 文件

- `idol_aliases.json`：程序直接读取的数据与规范化反向索引。
- `idol_aliases.sqlite`：SQLite 数据库，包含 groups、members、aliases、metadata、member_chinese 五张表。
- `姓名别名表.html`：内嵌数据库的可检索表格。
- `覆盖与来源.md`：每团收录数量、别名分类统计及全部引用页面。
- `source_names.json`：公开资料提取的姓名字段快照；不包含传记、图片、账号 cookies。
- `curated_overrides.json`：人工校正和补充旧艺名，记录来源。
- `chinese_names.json`：人工核对的中文写法、繁简对应和逐项来源，供继续扩充。
- `chinese_support.py`：中文字段、显示名选择规则和 SQLite 补充表生成。
- `build_database.py`：重建脚本。
- `check_database.py`：数据一致性及关键姓名检索验证。

## 覆盖与准确性

覆盖主流、近期、历代以及部分全球女团，保留原资料页中列出的现任、历史及部分出道前成员。这是一份有明确范围的搜索数据库，不是完整行业名录，也不是官方现役名单。“主流”采用人工选定的覆盖清单，没有客观排名含义。

同一艺人在不同团体中保留独立团体记录，例如 IZ*ONE 与 LE SSERAFIM、LOONA 与 ARTMS。记录总数是“团体—成员”数量，不是不同人物数量。即使韩文全名一样也不自动合并，例如 LE SSERAFIM、tripleS、APRIL 中的 김채원。数据库把冲突完整保留，后续必须结合团体判断身份。

主要姓名事实来自 [KProfiles](https://kprofiles.com/kpop-girl-groups/) 社区成员资料，并保留每条记录的准确页面链接。成员姓名字段已经过结构检查；不应把社区字段理解为逐项获得官方证实。

部分官方英文拼写另与 [TWICE 官方资料](https://www.twicejapan.com/feature/profile)、[LE SSERAFIM 官方资料](https://www.le-sserafim.jp/profile)、[IVE / Sony 官方资料](https://www.sonymusic.co.jp/artist/IVE/profile/) 交叉核对，标记为 `official_stage`。此核对仅支持这些别名，不代表全条记录或整个数据库已经官方认证。

KATSEYE 海外成员的韩文艺名另与官方 [Weverse 视频](https://weverse.io/katseye/media/3-134778902) 及 [Weverse LIVE 标题](https://weverse.io/katseye/live?hl=ko) 核对，标记为 `official_stage_hangul`；常用英文短全名另参考 [AP 采访](https://apnews.com/article/9b42686b193b16150fdc6371bca1dee1)。

`Nakyung` 保留为 [相关社区使用的拼写](https://www.reddit.com/r/nakyung/)，其全名连写以对应成员资料中的姓氏组合。另补充 Monday/LUNEDI、LE/Elly、Haram/Rami、Olivia Hye/HyeJu 等新旧艺名；来源在人工校正文件中。

不收录资料里的趣味英文名字，也排除海外成员被随意附加的趣味韩文姓氏；这些原字段仅在来源快照中留存。发现冲突时以人工校正为准，例如 Wonder Girls 的 Sunye：团体页写成顺序错误的 `순예`，独立资料支持 `선예`，已更正检索键。

## 别名的含义

| 类型 | 含义 | 后续搜索建议 |
| --- | --- | --- |
| official_stage | 官方页面出现的英文拼写 | 优先 |
| chinese_official_usage | 官方账号实际使用的中文写法，不代表唯一正名或法定汉字 | 优先，保留出处 |
| chinese_community_usage | 社区资料中出现的中文写法，未核实官方确认 | 中文输入匹配 |
| generated_chinese_script | 人工核对的繁简或字形转换 | 输入和显示转换，不能当作新的官方证据 |
| source_* | 社区资料中实际出现的艺名、全名、韩文及旧名 | 优先；保留来源可信度 |
| community_variant / curated_source_variant | 另有社区或补充资料支持的写法 | 常用别名层 |
| generated_format | 去空格、连字符或标点后的形式 | 适合输入识别，不必每种形式都独立联网查询 |
| generated_given_* | 从全名提取的短名 | 候选；必须检查同名冲突 |
| generated_romanization / generated_hangul_romanization | 保守音译变体或逐音节转写 | 低优先级补搜；未证明博主实际使用 |

`priority` 是搜索顺序的工程分值，不是事实可信度的统计概率。不能直接把所有别名一口气联网搜索。建议按成员、韩文、英文常用名、新旧艺名分层，必要时再尝试生成拼写。

大小写、空格、连字符和英文重音在规范化匹配时忽略，韩文 Unicode 分解/组合写法统一处理。例如 `Lee Na-gyung`、`Lee Na Gyung`、`leenagyung` 可认出同一条 fromis_9 记录。`Nakyung`、`나경` 可能也命中 tripleS 的 Kim Nakyoung；这是同名冲突，不能丢弃其中一人。

“全部可能写法”无法穷尽。当前生成规则没有全局等同 `seung/sung`、`eun/un` 等容易合并不同名字的字符串，也没有对所有拼写做任意编辑距离匹配。未知写法应作为未识别输入处理，或经过核对后加入人工补充文件。

## 重建与检查

在项目目录运行：

```powershell
.\.checkenv\Scripts\python.exe -X utf8 idol_names\build_database.py
.\.checkenv\Scripts\python.exe -X utf8 idol_names\check_database.py
```

默认从姓名快照重建；加 `--refresh` 才重新读取公开资料。生成器只写入本文件夹中的数据库、表格与姓名快照。在线资料可能变化，刷新结果必须再次审核；页面失效会列入 `fetch_failures`，不会自动编造成员。

SQLite 查找示例（查询参数应先按生成器中的 `normalize()` 处理）：

```sql
SELECT DISTINCT m.id, m.group_name, m.stage_name, m.stage_hangul
FROM aliases AS a JOIN members AS m ON m.id = a.member_id
WHERE a.normalized = 'leenagyung';
```

## 当前边界

姓名对应已提供；不能保证每个别名都能让 YouTube 搜到目标视频。源码中的单轮搜索会扩展常用英文/韩文姓名和 8 种日期写法，最多 23 个查询、同时 2 个网络检索，按匹配排序去重，最多展示 100 条结果。不是姓名/日期的全部笛卡尔积，也不扫描所有频道；YouTube 没返回的内容无法保证找全。结果标题必须同时匹配所选成员姓名（仅组合搜索时为组合名）和所填日期，否则剔除，不再显示近似结果。英文名按词边界匹配，避免 Lia 命中 Australian、Rei 命中 freight。标题没有日期、只写组合但未写所选成员的个人搜索结果也会被排除；不按视频语言一刀切过滤。发布时间带 ≈ 的是搜索接口估计值；缺失显示 —。点击结果“下载”后调用原有视频解析流程，再按原有界面选择格式和保存目录。

## 中文名状态与界面接入

首批补充 39 条成员记录，覆盖 fromis_9、TWICE、IVE、LE SSERAFIM、aespa、ITZY；其余 705 条记录保留 `pending`，没有凭韩文猜测汉字。这里不是整个数据库的中文名完善完成。

fromis_9 的五位成员标为 `official_usage`：依据是账号帖子实际使用的中文标签。它与 `official_confirmed`（明确的姓名确认或正名材料）分开；目前没有条目标为后者。其余首批名字均为 `community_usage`，即使百科声称获得公司邮件确认，也没有在本次核实原材料前升级为官方确认。

例如官方账号目前用“李采映”，社区成员表用“李彩煐”：显示名先选官方账号实际用法，两种都保留用于输入识别。频次只统计该拼写及明确繁简对应在本文件所引用的不同页面中出现的次数，不是搜索命中数或全网出现频次。同等级且同页数时沿用人工排列顺序，不能称为最常见。

JSON 成员新增 `chinese_name`（简体显示名或 null）、`chinese_name_status`、`chinese_names`（原样写法、简体转换、来源和统计）。SQLite 用独立 `member_chinese` 表，原有 members 表结构不变，别名仍通过 aliases 查询。数据版本为 2。

按后续要求，下载器已取消中文姓名输入检索和名字栏旁的中文名显示框，保留英文、韩文输入与身份选择。数据库及离线姓名表中的中文资料保留，但不参与下载器的检索查询。选过的成员对应关系用本地 QSettings 保存，下次输入同一别名优先恢复；明确选择不同组合时，组合条件优先。

双击项目根目录唯一的 `check_ytdl.bat` 可启动源码版测试，先检查语法、导入和离线检索规则。日期须填写有效的六位 YYMMDD。组合和成员至少填写其中之一。“搜索”按钮位于组合、名字、日期输入行最右侧。成员候选优先显示完整姓名，韩文姓名对应的英文全名按姓在前、各段空格分隔且无连字符；西方姓名保留来源原名。姓名匹配不跨越省略号、其他词或倒序拼接。切换应用、隐藏主窗口或点击其他控件时关闭姓名候选，不设置全局置顶。结果列表可用链接栏右侧箭头反复打开/收起；关闭列表不丢失本次结果，重新搜索才替换结果。搜索过程中“搜索”按钮变为“取消”。
