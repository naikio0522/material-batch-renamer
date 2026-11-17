"""Startup update check for the Windows packaged application.

The manifest must be served from a repository controlled by the publisher.  A
release includes version, date, notes, download_url and sha256 (see the sample).
Call startup_update_check(root, manifest_url, repository) after creating root;
if it returns False the caller must destroy root and terminate the process.
"""

import datetime
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import ttk

CURRENT_VERSION = '1.0'
MAX_MANIFEST_BYTES = 128 * 1024
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
_HOSTS = {'github.com', 'raw.githubusercontent.com', 'release-assets.githubusercontent.com',
          'objects.githubusercontent.com'}


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+){0,3}', value):
        raise ValueError('版本号格式不正确。')
    return tuple(int(x) for x in value.split('.'))


def is_newer(remote, current=CURRENT_VERSION):
    a, b = _version(remote), _version(current)
    length = max(len(a), len(b))
    return a + (0,) * (length - len(a)) > b + (0,) * (length - len(b))


def validate_manifest(raw, repository):
    """Validate untrusted metadata and bind downloads to the configured repo."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository or ''):
        raise ValueError('更新仓库配置不正确。')
    if not isinstance(raw, dict):
        raise ValueError('更新信息格式不正确。')
    version = raw.get('version')
    _version(version)
    date = raw.get('date')
    if not isinstance(date, str):
        raise ValueError('更新日期格式不正确。')
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ValueError('更新日期格式不正确。') from None
    notes = raw.get('notes')
    if not isinstance(notes, str) or not notes.strip() or len(notes) > 12000:
        raise ValueError('更新公告内容不正确。')
    url = raw.get('download_url')
    if not isinstance(url, str):
        raise ValueError('更新下载地址不正确。')
    parsed = urllib.parse.urlsplit(url)
    path = urllib.parse.unquote(parsed.path)
    required_prefix = '/' + repository + '/releases/download/'
    if (parsed.scheme != 'https' or parsed.hostname != 'github.com' or
            parsed.username or parsed.password or parsed.port not in (None, 443) or
            not path.casefold().startswith(required_prefix.casefold()) or
            not path.casefold().endswith('.exe') or parsed.fragment):
        raise ValueError('更新下载地址不是指定仓库的 GitHub 安装包。')
    digest = raw.get('sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[A-Fa-f0-9]{64}', digest):
        raise ValueError('更新包校验值不正确。')
    return {'version': version, 'date': date, 'notes': notes,
            'download_url': url, 'sha256': digest.lower()}


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if (parsed.scheme != 'https' or parsed.hostname not in _HOSTS or
                parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError('更新服务跳转到了不受信任的地址。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in _HOSTS or
            parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('更新地址不安全。')
    opener = urllib.request.build_opener(_SafeRedirect())
    return opener.open(urllib.request.Request(url, headers={'User-Agent': 'MaterialRenamer-Updater/1.0',
                                                           'Cache-Control': 'no-cache'}), timeout=15)


def fetch_manifest(url, repository):
    parsed = urllib.parse.urlsplit(url)
    query = parsed.query + ('&' if parsed.query else '') + 'update_check=' + str(time.time_ns())
    check_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
    with _open(check_url) as response:
        data = response.read(MAX_MANIFEST_BYTES + 1)
    if len(data) > MAX_MANIFEST_BYTES:
        raise ValueError('更新信息过大。')
    try:
        raw = json.loads(data.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('更新信息读取失败。') from None
    return validate_manifest(raw, repository)


def download_update(manifest, target_dir, cancel=None):
    """Download into the executable directory, checking size and SHA-256."""
    fd, path = tempfile.mkstemp(prefix='.material-update-', suffix='.exe', dir=target_dir)
    digest, size = hashlib.sha256(), 0
    try:
        with os.fdopen(fd, 'wb') as output, _open(manifest['download_url']) as response:
            while True:
                if cancel is not None and cancel.is_set():
                    raise RuntimeError('已取消下载。')
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError('更新包过大。')
                digest.update(chunk)
                output.write(chunk)
        if cancel is not None and cancel.is_set():
            raise RuntimeError('已取消下载。')
        if size == 0 or digest.hexdigest() != manifest['sha256']:
            raise ValueError('更新包校验失败，未安装。')
        return path
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


_HELPER = r'''param([string]$CurrentExe, [string]$NewExe, [int]$OldPid)
$ErrorActionPreference = 'Stop'
$backup = "$CurrentExe.backup-$([guid]::NewGuid().ToString('N'))"
$log = Join-Path $env:TEMP 'material-renamer-update-error.log'
try {
    Wait-Process -Id $OldPid -Timeout 45 -ErrorAction SilentlyContinue
    if (Get-Process -Id $OldPid -ErrorAction SilentlyContinue) { throw 'Old process did not exit.' }
    # PyInstaller one-file has a bootloader parent that may briefly retain the
    # executable after the Python child exits. Wait for the file to be released.
    $moved = $false
    for ($i = 0; $i -lt 60; $i++) {
        try { Move-Item -LiteralPath $CurrentExe -Destination $backup; $moved = $true; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $moved) { throw 'Could not replace the existing executable.' }
    try {
        Move-Item -LiteralPath $NewExe -Destination $CurrentExe
        $newProcess = Start-Process -FilePath $CurrentExe -PassThru
        Start-Sleep -Seconds 3
        $newProcess.Refresh()
        if ($newProcess.HasExited -and $newProcess.ExitCode -ne 0) { throw 'Updated process could not start.' }
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    } catch {
        if (Test-Path -LiteralPath $CurrentExe) { Remove-Item -LiteralPath $CurrentExe -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $CurrentExe }
        throw
    }
} catch {
    try { Add-Content -LiteralPath $log -Value "$(Get-Date -Format o): $($_.Exception.Message)" } catch { }
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $message = '自动更新未完成，软件将尝试恢复原版本。请检查文件权限或关闭占用软件后重试。'
        if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $CurrentExe)) {
            $message += "`n原版本备份位于：$backup"
        }
        [void][System.Windows.Forms.MessageBox]::Show($message, '更新失败')
    } catch { }
    if (Test-Path -LiteralPath $CurrentExe) { Start-Process -FilePath $CurrentExe -ErrorAction SilentlyContinue }
} finally {
    if (Test-Path -LiteralPath $NewExe) { Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}
'''


def start_installer(downloaded_path):
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        raise RuntimeError('请使用 Windows 打包版进行自动更新，源代码不会被覆盖。')
    current = str(Path(sys.executable).resolve())
    with tempfile.NamedTemporaryFile('w', suffix='.ps1', prefix='material-renamer-update-',
                                     delete=False, encoding='utf-8-sig') as script:
        script.write(_HELPER)
        helper = script.name
    try:
        subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                          '-File', helper, '-CurrentExe', current, '-NewExe', downloaded_path,
                          '-OldPid', str(os.getpid())],
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
    except Exception:
        try:
            os.remove(helper)
        except OSError:
            pass
        raise


def startup_update_check(root, manifest_url, repository):
    """Show modal startup check. False means caller must immediately exit."""
    dialog = tk.Toplevel(root)
    dialog.title('检查更新')
    dialog.geometry('520x300')
    dialog.resizable(False, False)
    if root.state() != 'withdrawn':
        dialog.transient(root)
    dialog.grab_set()
    title = ttk.Label(dialog, text='正在检查更新…', font=('Microsoft YaHei UI', 11, 'bold'))
    title.pack(anchor='w', padx=18, pady=(16, 8))
    body_frame = ttk.Frame(dialog)
    body_frame.pack(fill='both', expand=True, padx=18)
    body = tk.Text(body_frame, height=8, wrap='word', relief='flat', background=dialog.cget('background'))
    body_scroll = ttk.Scrollbar(body_frame, orient='vertical', command=body.yview)
    body.configure(yscrollcommand=body_scroll.set)
    body_scroll.pack(side='right', fill='y')
    body.pack(side='left', fill='both', expand=True)
    controls = ttk.Frame(dialog)
    controls.pack(fill='x', padx=18, pady=14)
    status = ttk.Label(controls, text='请稍候…')
    status.pack(side='left')
    events = queue.Queue()
    state = {'result': False, 'manifest': None, 'operation': None,
             'running': False, 'cancel': threading.Event(), 'after_id': None}

    def show_body(text):
        body.configure(state='normal')
        body.delete('1.0', 'end')
        body.insert('1.0', text)
        body.configure(state='disabled')

    def clear_buttons():
        for widget in controls.winfo_children():
            if widget is not status:
                widget.destroy()

    def finish(value):
        state['result'] = value
        if state['after_id'] is not None:
            try:
                dialog.after_cancel(state['after_id'])
            except tk.TclError:
                pass
            state['after_id'] = None
        dialog.destroy()

    def close_dialog():
        # Closing never bypasses a known mandatory update.
        if state['running'] and state['operation'] == 'download':
            state['cancel'].set()
            status.configure(text='正在取消下载…')
        else:
            finish(False)

    dialog.protocol('WM_DELETE_WINDOW', close_dialog)

    def worker(operation):
        try:
            if operation == 'check':
                result = fetch_manifest(manifest_url, repository)
            else:
                if os.name != 'nt' or not getattr(sys, 'frozen', False):
                    raise RuntimeError('请使用 Windows 打包版更新；源代码不会被覆盖。')
                result = download_update(state['manifest'], str(Path(sys.executable).resolve().parent), state['cancel'])
            events.put((operation, result, None))
        except Exception as exc:
            events.put((operation, None, str(exc) or type(exc).__name__))

    def start(operation):
        state['operation'] = operation
        state['running'] = True
        state['cancel'].clear()
        clear_buttons()
        status.configure(text='正在检查，请稍候…' if operation == 'check' else '正在下载并校验，请稍候…')
        threading.Thread(target=worker, args=(operation,), daemon=True).start()

    def poll():
        state['after_id'] = None
        try:
            operation, value, error = events.get_nowait()
        except queue.Empty:
            state['after_id'] = dialog.after(100, poll)
            return
        state['running'] = False
        if state['cancel'].is_set():
            if operation == 'download' and value:
                try:
                    os.remove(value)
                except OSError:
                    pass
            finish(False)
            return
        if error:
            title.configure(text='检查更新失败' if operation == 'check' else '更新未完成')
            if operation == 'check':
                show_body('暂时无法检查是否有新版本：' + error + '\n\n可以重试，或暂时打开软件。')
            else:
                show_body('无法完成更新：' + error + '\n\n请检查网络后重试。')
            status.configure(text='')
            ttk.Button(controls, text='重试', command=lambda: start(operation)).pack(side='right', padx=4)
            ttk.Button(controls, text='退出软件', command=lambda: finish(False)).pack(side='right', padx=4)
            if operation == 'check' and state['manifest'] is None:
                ttk.Button(controls, text='暂时打开软件', command=lambda: finish(True)).pack(side='right', padx=4)
        elif operation == 'check':
            if not is_newer(value['version']):
                finish(True)
                return
            state['manifest'] = value
            title.configure(text=value['date'] + ' 更新公告')
            show_body('发现新版本 ' + value['version'] + '，需要更新后才能继续使用。\n\n' + value['notes'])
            status.configure(text='')
            ttk.Button(controls, text='下载并更新', command=lambda: start('download')).pack(side='right', padx=4)
            ttk.Button(controls, text='退出软件', command=lambda: finish(False)).pack(side='right', padx=4)
        else:
            try:
                start_installer(value)
            except Exception as exc:
                try:
                    os.remove(value)
                except OSError:
                    pass
                title.configure(text='更新未完成')
                show_body('无法启动更新：' + str(exc))
                status.configure(text='')
                ttk.Button(controls, text='重试', command=lambda: start('download')).pack(side='right', padx=4)
                ttk.Button(controls, text='退出软件', command=lambda: finish(False)).pack(side='right', padx=4)
            else:
                finish(False)
                return
        state['after_id'] = dialog.after(100, poll)

    show_body('正在查看是否有新版本。')
    start('check')
    state['after_id'] = dialog.after(100, poll)
    root.wait_window(dialog)
    return state['result']
