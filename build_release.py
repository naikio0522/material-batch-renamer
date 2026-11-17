"""Build a Windows one-file release and attach its actual source version.

Run from the project directory with ``python build_release.py 1.3``. The
requested version is set in an isolated temporary source copy, never in the
user's existing files. Requires Python, tkinterdnd2 and PyInstaller.
"""
import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from package_metadata import append_build_metadata, read_build_version


def source_version(path):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == 'CURRENT_VERSION' for target in node.targets)]
    if len(matches) != 1 or not isinstance(matches[0].value, ast.Constant):
        raise ValueError('无法读取唯一的软件内部版本号。')
    version = matches[0].value.value
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}', version):
        raise ValueError('软件内部版本号格式无效。')
    return version


def set_staged_version(path, version):
    """Modify only an isolated staging copy and verify the resulting AST."""
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}', version):
        raise ValueError('版本号请使用 1.2 或 1.2.3 这样的格式。')
    path = Path(path)
    source_version(path)
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text)
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == 'CURRENT_VERSION' for target in node.targets)]
    item = matches[0]
    if item.lineno != item.end_lineno or len(item.targets) != 1:
        raise ValueError('软件内部版本号必须是单行赋值。')
    lines = text.splitlines(keepends=True)
    previous = lines[item.lineno - 1]
    suffix = '\r\n' if previous.endswith('\r\n') else ('\n' if previous.endswith('\n') else '')
    lines[item.lineno - 1] = 'CURRENT_VERSION = ' + repr(version) + suffix
    path.write_text(''.join(lines), encoding='utf-8')
    if source_version(path) != version: raise ValueError('无法设置隔离副本的版本号。')


def build(target_version=None):
    if os.name != 'nt': raise RuntimeError('请在 Windows 上执行打包。')
    root = Path(__file__).resolve().parent
    current_version = source_version(root / 'updater.py')
    version = target_version or current_version
    if not re.fullmatch(r'[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}', version):
        raise ValueError('版本号请使用 1.2 或 1.2.3 这样的格式。')
    destination = root / 'dist' / 'material-renamer.exe'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='material-renamer-build-') as temp:
        scratch = Path(temp)
        source = scratch / 'source'
        source.mkdir()
        for name in ('app.py', 'rename_core.py', 'updater.py', 'settings.py', 'layout_schema.py'):
            shutil.copy2(root / name, source / name)
        set_staged_version(source / 'updater.py', version)
        cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
               '--name', 'material-renamer', '--distpath', str(scratch / 'dist'),
               '--workpath', str(scratch / 'work'), '--specpath', str(scratch), str(source / 'app.py')]
        subprocess.run(cmd, cwd=str(source), check=True)
        package = scratch / 'dist' / 'material-renamer.exe'
        append_build_metadata(package, version)
        if read_build_version(package) != version: raise RuntimeError('打包后版本核对失败。')
        os.replace(package, destination)
    print('已生成', destination)
    print('安装包内部版本：', version)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description='打包带版本校验标记的软件，不修改现有源文件。')
        parser.add_argument('version', nargs='?', help='新版本号，如 1.3；省略时使用源代码版本')
        build(parser.parse_args().version)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('打包未完成：', exc, file=sys.stderr)
        sys.exit(1)
