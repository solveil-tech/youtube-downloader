# YouTube Downloader

一个基于 PyQt6 与 yt-dlp 的 Windows 桌面视频下载器，提供格式筛选、片段预览、多任务下载和多语言界面。

## 功能

- 解析并显示视频标题、作者、时长和封面
- 仅列出可直接获取且无需转码的视频/音频组合
- 显示分辨率、帧率、容器、编码和预计大小
- 支持 H.264、VP9、AV1 等来源实际提供的编码
- 按组合、成员及六位日期搜索舞台视频，支持名字别名、日期格式变化和 Shorts
- 曲目可从本地数据库自动补全并填入所属组合，也可手动输入；搜索输入与必要词条筛选独立
- 可开启日期容错，补充表演当天至之后第 14 天发布的无日期标题视频；发布日期须核实，结果按视频 ID 去重
- 下载完成后检查文件、时长、音轨数据连续性，并对首段、中段、末段抽样解码；异常只提示，不自动删除文件
- 搜索结果支持多选、复制链接、跳转网页及已下载视频提示
- 多选视频批量解析、默认格式下载、封面叠放选择及保存全部封面；只选一个时保留全部单视频功能
- 解析后自动缓存最高 720p 的带音频预览，支持片段播放、倍速、逐帧调整和毫秒级区间选择
- 仅显示最新十个下载任务，额外任务仍排队处理，并行任务数可设为 1–5
- 任务支持暂停、继续、重试、清除、隐藏、复制链接和打开视频页面
- 多流累计进度、平滑速度及 ETA
- 网络中断自动重试并动态降低并行数，失败后可展开和复制错误详情
- 磁盘空间检查、重名处理及 yt-dlp 下载引擎检查更新
- 记忆上次保存目录、颜色模式和界面语言
- 统一半透明无箭头滚动条，支持平滑滚动，滚轮步长约为原来的 70%
- 中文、英语、日语、韩语、法语、德语、俄语、意大利语、西班牙语和阿拉伯语

## 使用

1. 下载仓库中的 `ytdl.exe`，可直接复制到桌面运行；下载引擎、应用图标和数据库已内置。
2. 确保系统已安装 [FFmpeg](https://ffmpeg.org/) 并可从 `PATH` 调用；高画质音视频合并和片段下载需要 FFmpeg。
3. 运行 `ytdl.exe`，粘贴 YouTube 链接并解析。

`cookies.txt` 是可选文件。需要账号授权的视频可以在 `%LOCALAPPDATA%\Solveil\YoutubeDownloader`（也兼容程序目录）自行放置 Netscape 格式的 cookies 文件。不要把自己的 `cookies.txt` 上传到公开仓库或发送给他人。

## 从源码运行

需要 Python 3.11 或更高版本：

Windows 用户可以直接双击 `check_ytdl.bat`。它会创建独立的 `.checkenv`、自动安装依赖、检查源码并启动程序。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\ytdl.py
```

## 构建 EXE

```powershell
.\build.ps1
```

输出文件位于 `dist\ytdl.exe`。构建脚本和 `ytdl.spec` 会排除可能与 Qt 冲突的宿主 ICU DLL，并补充 PyQt6 所需的 Visual C++ 运行库。

## 项目文件

### 数据库独立更新

界面右上角的数据库图标提供“从 GitHub 更新数据库”“导入本地数据库”和“重新读取数据库”。在线更新从本项目仓库获取成员及曲目 JSON，不下载或执行代码；两份数据固定到同一 Git 提交，校验通过后整体替换并立即刷新输入框候选项，不需要重启或重新打包 EXE。

也可导入 `idol_names/idol_aliases.json`（同目录的 `song_catalogue.json` 会一并导入）、单独的 `song_catalogue.json`，或已保存的 `search_database.json`。独立更新保存到 `%LOCALAPPDATA%\Solveil\YoutubeDownloader\idol_names\search_database.json`，下次打开继续使用，不会在桌面生成数据库文件。无效或不兼容的数据会提示原因并保留当前数据；启动时外部数据库损坏则回退到内置数据库。仅修改数据库结构或软件功能时才需要更新 EXE。

本次补充 Baby DONT Cry：Yihyun、Kumi、Mia、Beni 的英韩艺名、来源标注的本名及检索变体，并收录已核实的八首非 remix 曲目。官方艺名与曲目参考 [P NATION](https://pnation.com/releases/119)、[I DONT CARE](https://pnation.com/releases/123) 和 [AFTER CRY](https://pnation.com/releases/128)；本名参考社区资料，未宣称均获官方确认。

### 桌面运行与数据存放

可以将 `ytdl.exe` 复制到桌面运行。查重缓存、下载来源索引、启动错误日志、曲目更新缓存及更新后的下载引擎保存在 `%LOCALAPPDATA%\Solveil\YoutubeDownloader`，不再写到 EXE 旁边。语言、主题、上次打开的文件夹等偏好仍使用原来的 Windows 设置保存方式。

旧 EXE 旁的查重缓存及来源索引在新数据目录没有对应文件时自动复制过去，旧文件不会删除。已存在的桌面 JSON 不会自动消失，确认新版本正常运行并保留下载记录后可自行整理。视频和封面仍保存到你选择的下载文件夹。

若需要登录凭据，可将外部 `cookies.txt` 放入上述应用数据目录；也兼容放在 EXE 旁边。凭据不会内置或上传。本机运行完整视频合并、片段处理和检查还需要可用的 FFmpeg/FFprobe；当前构建不内置这两个外部工具。

K-pop 搜索默认折叠；搜索结果支持匹配优先、发布时间和时长排序，完全匹配内优先普通视频而非 Shorts。勾选结果保持悬浮色高亮，已下载提示显示 ✔。

- `ytdl.py`：应用源码
- `idol_search.py`、`youtube_search.py`：身份匹配、搜索及 Shorts 元信息解析
- `idol_names/`：成员别名数据库、来源说明与生成脚本（EXE 内置运行所需数据库）
- `media_library.py`：本地视频查重提示
- `download_check.py`：只读下载结果检查
- `result_player.py`：搜索结果播放窗口，支持独立音轨、暂停、跳转、音量和全屏
- `song_catalogue.py`：曲目目录获取、版本去重与本地缓存
- `ytdl.exe`：Windows 单文件版本
- `yt_dlp.exe`：yt-dlp 下载引擎
- `icon.ico`：应用图标
- `requirements.txt`：Python 依赖
- `check_ytdl.bat`：一键准备检查环境并运行源码
- `ytdl.spec`、`build.ps1`：可复现构建配置
- `check_*.py`：搜索、界面、批量下载及本地媒体的回归检查

## 说明

曲目目录直接读取 `idol_names/song_catalogue.json`，运行时不请求在线音乐目录，刷新按钮仅重新读取本地文件。数据来源包含 Kprofiles 的组合发行曲目列表和此前核实的 Apple Music 曲目，逐项保留来源链接。维护脚本 `idol_names/collect_local_songs.py` 不由软件自动运行。排除 remix、instrumental、karaoke、sped-up、slowed 等版本；各组收录范围并不保证穷尽所有歌曲，缺失曲目仍可手动输入。不能把曲目库覆盖组合数等同于完整历史发行覆盖，也不自动猜测韩文歌名与英文歌名的翻译关系。

搜索输入至少包含组合+曲目、组合+日期、曲目+成员、曲目+日期、成员+日期中的一组；日期可留空。默认要求所有已填写词条匹配标题，打开详细筛选可独立调整组合、曲目、成员、日期是否必含，取消勾选不清空输入。组合栏清空后不把成员所属组合隐式加入搜索。日期容错开关补充所选日期起14天内发布的视频，公开发布日期必须核实，无法核实的补充结果不展示。发布日期不等于表演日期，仍需自行确认舞台。网络搜索不能保证穷尽所有符合条件的视频。

下载检查使用 [FFprobe](https://ffmpeg.org/ffprobe.html) 和 FFmpeg，不改写视频。检查通过表示元信息、音频数据连续性和抽样解码未发现异常，不保证每一帧无损坏，也不保证所有系统播放器都支持对应编码；原视频本身的无声内容不作为音频数据缺失处理。

请遵守网站服务条款、版权规定及所在地法律，仅下载你有权保存的内容。本项目与 YouTube、Google 和 yt-dlp 项目无隶属关系。

## License

本项目采用 GNU GPL v3 or later。第三方组件分别遵循其各自许可证。
