# 素材批量重命名工具

Windows 桌面软件，当前版本 **1.3.2**。从 [Releases](https://github.com/naikio0522/material-batch-renamer/releases) 下载 `material-renamer.exe`，双击运行，无需安装 Python。使用 1.3 或更早版本时，请手动下载并打开新版一次，以避开旧版更新后重启失败的问题。

支持素材分类命名、运营平均分配、指定或自动序号、部分素材勾选重命名、结果预览及文件重名保护。列表列标题可拖动换位，个人填写内容和窗口设置会保存。软件启动时自动检查更新，标题旁也可手动检查。发现新版后须更新或退出；检查失败时可暂时打开软件。

序号默认为 `#`，按勾选素材的列表顺序输出 1、2、3……；填写数字时，各素材使用该固定值。序号位于日期之后、一级分类之前。

使用方法见 [使用说明](使用说明.txt)，发布步骤见 [发布和更新说明](发布和更新说明.md)。开发者管理工具为独立程序，正式版没有后台入口。

## 从源码运行或打包

需要 Windows、Python 3.13 和 Tkinter：

```powershell
python -m pip install -r requirements.txt
python app.py
```

打包正式版本：

```powershell
python build_release.py
```

生成 `dist\material-renamer.exe`，附带由源码版本生成的完整性标记。该标记用于核对版本、防止误传，不能代替数字签名。
