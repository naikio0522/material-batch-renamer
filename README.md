# 素材批量重命名工具

Windows 桌面工具，支持批量生成素材名称、自动分配运营、预览及重名检查。使用方法见 [使用说明](使用说明.txt)。

## 下载与使用

从本仓库的 [Releases](https://github.com/naikio0522/material-batch-renamer/releases) 下载最新的 `material-renamer.exe`，在 Windows 上双击运行，无需安装 Python。

软件启动时会从本仓库的 `update.json` 检查版本。发现比当前版本新的版本后，会显示更新公告；必须更新或退出，才能继续。暂时无法检查时，可以重试或暂时打开软件。

## 发布新版与修改公告

参见 [发布和更新说明](发布和更新说明.md)。仓库根目录的 `update.json` 控制版本号、更新日期、公告文字、下载地址及安装包校验值。请先上传新版安装包，再更新 `update.json`，避免用户遇到无法下载的更新。

## 从源代码运行

需要 Windows、Python 3.13 和 Tkinter。在仓库目录打开 PowerShell：

```powershell
python -m pip install -r requirements.txt
python app.py
```

自动替换程序仅适用于打包后的 Windows exe。请勿在仓库、更新公告或发布包中加入访问令牌、密码或私人资料。
