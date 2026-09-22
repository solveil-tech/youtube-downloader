# YouTube Downloader

一个基于 PyQt6 与 yt-dlp 的 Windows 桌面视频下载器，提供格式筛选、片段预览、多任务下载和多语言界面。

## 功能

- 解析并显示视频标题、作者、时长和封面
- 仅列出可直接获取且无需转码的视频/音频组合
- 显示分辨率、帧率、容器、编码和预计大小
- 支持 H.264、VP9、AV1 等来源实际提供的编码
- 片段预览、逐帧调整和毫秒级区间选择
- 最多保留五个下载任务，支持暂停、继续、清除和隐藏
- 多流累计进度、平滑速度及 ETA
- 自动重试、磁盘空间检查和重名处理
- 记忆上次保存目录、颜色模式和界面语言
- 中文、英语、日语、韩语、法语、德语、俄语、意大利语、西班牙语和阿拉伯语

## 使用

1. 下载仓库中的 `ytdl.exe`、`yt_dlp.exe` 和 `icon.ico`，放在同一目录。
2. 确保系统已安装 [FFmpeg](https://ffmpeg.org/) 并可从 `PATH` 调用；高画质音视频合并和片段下载需要 FFmpeg。
3. 运行 `ytdl.exe`，粘贴 YouTube 链接并解析。

`cookies.txt` 是可选文件。需要账号授权的视频可以在程序目录自行放置 Netscape 格式的 cookies 文件。不要把自己的 `cookies.txt` 上传到公开仓库或发送给他人。

## 从源码运行

需要 Python 3.12：

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

- `ytdl.py`：应用源码
- `ytdl.exe`：Windows 单文件版本
- `yt_dlp.exe`：yt-dlp 下载引擎
- `icon.ico`：应用图标
- `requirements.txt`：Python 依赖
- `ytdl.spec`、`build.ps1`：可复现构建配置

## 说明

请遵守网站服务条款、版权规定及所在地法律，仅下载你有权保存的内容。本项目与 YouTube、Google 和 yt-dlp 项目无隶属关系。

## License

本项目采用 GNU GPL v3 or later。第三方组件分别遵循其各自许可证。
