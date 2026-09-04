"""停止「小说写作助手」服务。

结束正在运行 app.py 的 Flask 服务进程。由于 app.py 以 debug=True 启动，
Flask 会使用 reloader，形成「父进程（reloader）+ 子进程（实际服务）」两层，
本脚本会一并结束整棵进程树，避免父进程重新拉起子进程。

用法：
    python stop_server.py
"""

import sys

try:
    import psutil
except ImportError:  # 未安装 psutil 时回退到 PowerShell 方案
    psutil = None


def _is_app_server(proc):
    """判断该进程是否为运行 app.py 的服务进程。"""
    if psutil is None:
        return False
    try:
        cmdline = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    for arg in cmdline:
        arg = (arg or "").replace("\\", "/")
        if arg == "app.py" or arg.endswith("/app.py"):
            return True
    return False


def _ppid_safe(proc):
    """安全读取父进程 ID，失败返回 None。"""
    try:
        return proc.ppid()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _stop_with_psutil():
    procs = [p for p in psutil.process_iter() if _is_app_server(p)]
    if not procs:
        print("未发现运行中的 app.py 服务。")
        return 0

    pids = {p.pid for p in procs}
    # 顶层进程：父进程不在本次匹配集合里（即 Flask reloader 父进程）
    roots = [p for p in procs if _ppid_safe(p) not in pids]
    if not roots:
        roots = procs  # 兜底：未能识别顶层时，直接处理全部匹配进程

    killed = set()
    for root in roots:
        try:
            children = root.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            children = []
        # 先结束父进程，避免 watchdog 在子进程退出后重新拉起
        try:
            root.terminate()
            killed.add(root.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        for child in children:
            if child.pid not in killed:
                try:
                    child.terminate()
                    killed.add(child.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

    # 等待退出，超时仍未退出的强制结束
    _, alive = psutil.wait_procs(procs, timeout=3)
    for p in alive:
        try:
            p.kill()
            killed.add(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print("已停止服务进程 PID：" + ", ".join(str(i) for i in sorted(killed)))
    return 0


def _stop_with_powershell():
    """无 psutil 时的 Windows 回退方案。"""
    import subprocess
    script = (
        "$ps = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'app\\.py' };"
        "if (-not $ps) { Write-Output 'NO_PROCESS'; exit 0 };"
        "$pids = @($ps | ForEach-Object { [int]$_.ProcessId });"
        "$roots = @($ps | Where-Object { $pids -notcontains [int]$_.ParentProcessId });"
        "foreach ($r in $roots) { taskkill /F /T /PID $r.ProcessId | Out-Null };"
        "Write-Output 'STOPPED'"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True,
    )
    text = (out.stdout or "").strip()
    print(text or (out.stderr or "").strip())
    return 0 if "NO_PROCESS" in text or "STOPPED" in text else 1


def main():
    if psutil is None:
        print("提示：未安装 psutil，改用 PowerShell 结束进程…")
        return _stop_with_powershell()
    return _stop_with_psutil()


if __name__ == "__main__":
    sys.exit(main())
