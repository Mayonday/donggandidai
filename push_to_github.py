# -*- coding: utf-8 -*-
"""配置 GitHub 远程仓库并推送（一键）。

用法：
    python push_to_github.py --repo-url https://github.com/<用户名>/<仓库名>.git

为什么用 Python 而不是 .ps1：
    Windows 默认的 PowerShell 执行策略会拒绝运行 .ps1 脚本
    （SecurityError: 在此系统上禁止运行脚本）。而本项目本来就需要 Python，
    且 Python 不受执行策略限制，跨平台（Linux/macOS）也能用。

做的事：
    1. 校验当前目录是 git 仓库、检查工作区是否干净
    2. 配置/更新 origin 远程地址
    3. 若远程已有初始提交（建仓时勾了 README / License 的情况），
       先把本地提交 rebase 到其上 —— 否则 push 会因 "rejected (fetch first)" 失败，
       这是首次推送最常见的失败原因
    4. 推送 main 分支并建立上游跟踪

首次推送时 Git Credential Manager 会弹出浏览器要求登录 GitHub，
本脚本不需要也不应接收任何密码或 token。
"""
import argparse
import re
import subprocess
import sys

GITHUB_RE = re.compile(r"^(https://github\.com/[\w.\-]+/[\w.\-]+?(\.git)?"
                       r"|git@github\.com:[\w.\-]+/[\w.\-]+?(\.git)?)$")


def run(cmd, check=False):
    """执行命令，返回 (returncode, stdout+stderr)。"""
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        die(f"命令失败：{' '.join(cmd)}\n{out.strip()}")
    return p.returncode, out


def info(m): print(f"[INFO] {m}")
def ok(m):   print(f"[ OK ] {m}")
def warn(m): print(f"[WARN] {m}", file=sys.stderr)
def die(m):
    print(f"[FAIL] {m}", file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="配置 GitHub 远程仓库并推送")
    ap.add_argument("--repo-url", required=True,
                    help="GitHub 仓库地址，如 https://github.com/user/repo.git")
    ap.add_argument("--branch", default="main", help="要推送的分支名（默认 main）")
    ap.add_argument("--remote", default="origin", help="远程名（默认 origin）")
    args = ap.parse_args()

    repo_url, remote = args.repo_url.strip(), args.remote

    # ---------- 0. 参数与仓库校验 ----------
    if not GITHUB_RE.match(repo_url):
        die(f"仓库地址格式不像 GitHub 地址：{repo_url}\n"
            "       期望形如 https://github.com/用户名/仓库名.git")

    if run(["git", "rev-parse", "--git-dir"])[0] != 0:
        die("当前目录不是 git 仓库。请在仓库根目录运行本脚本。")
    ok("当前目录是 git 仓库")

    # ---------- 1. 分支与工作区检查 ----------
    rc, out = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=True)
    branch = out.strip()
    if branch != args.branch:
        warn(f"当前分支是 '{branch}'，不是 '{args.branch}'。将推送 '{branch}'。")

    rc, out = run(["git", "status", "--porcelain"])
    dirty = [l for l in out.splitlines() if l.strip()]
    if dirty:
        warn(f"工作区有 {len(dirty)} 项未提交改动：")
        for l in dirty[:8]:
            print(f"        {l}")
        warn("建议先提交，否则推送的是上一次提交的内容。")
    else:
        ok("工作区干净，将推送最新提交")

    rc, out = run(["git", "log", "-1", "--oneline"], check=True)
    info(f"待推送提交：{out.strip()}")

    # ---------- 2. 配置远程 ----------
    rc, out = run(["git", "remote"])
    remotes = out.split()
    if remote in remotes:
        rc, cur = run(["git", "remote", "get-url", remote], check=True)
        cur = cur.strip()
        if cur != repo_url:
            info(f"更新远程 {remote}：{cur}  ->  {repo_url}")
            run(["git", "remote", "set-url", remote, repo_url], check=True)
        else:
            info(f"远程 {remote} 已指向 {repo_url}")
    else:
        info(f"添加远程 {remote}：{repo_url}")
        run(["git", "remote", "add", remote, repo_url], check=True)
    ok("远程配置完成")

    # ---------- 3. 远程已有提交则先 rebase ----------
    info("检查远程分支状态（若仓库不存在或需要登录，此处可能提示）...")
    rc, out = run(["git", "fetch", remote, "--prune"])
    fetch_failed = rc != 0
    for line in out.strip().splitlines():
        print(f"        {line}")

    ref = f"refs/remotes/{remote}/{branch}"
    has_remote_branch = run(["git", "show-ref", "--verify", "--quiet", ref])[0] == 0

    if fetch_failed and not has_remote_branch:
        die("无法访问远程仓库。请确认：\n"
            "       1) 仓库已在 GitHub 上创建（空仓库也可以）\n"
            "       2) 地址与用户名正确\n"
            "       3) 网络 / 代理可用")

    if has_remote_branch:
        ahead = int(run(["git", "rev-list", "--count", f"{remote}/{branch}..HEAD"],
                        check=True)[1].strip() or 0)
        behind = int(run(["git", "rev-list", "--count", f"HEAD..{remote}/{branch}"],
                         check=True)[1].strip() or 0)
        info(f"相对远程：领先 {ahead} 个提交，落后 {behind} 个提交")

        if behind > 0:
            warn("远程已有本地没有的提交（常见于建仓时勾选了 README / License）。")
            info("将本地提交变基到远程之上，避免推送被拒绝...")
            rc, out = run(["git", "rebase", f"{remote}/{branch}"])
            if rc != 0:
                print(out, file=sys.stderr)
                die("变基出现冲突，需要人工处理：\n"
                    "        git status                      # 查看冲突文件\n"
                    "        # 解决后： git add <文件> ; git rebase --continue\n"
                    "        # 放弃：   git rebase --abort\n"
                    "      处理完成后重新运行本脚本。")
            ok("变基完成")
    else:
        info(f"远程尚无 '{branch}' 分支（全新空仓库），可直接推送")

    # ---------- 4. 推送 ----------
    info("开始推送（首次会弹出浏览器要求登录 GitHub，请在浏览器中完成授权）...")
    rc, out = run(["git", "push", "-u", remote, branch])
    print(out.strip())
    if rc != 0:
        die("推送失败。常见原因：\n"
            "       1) 仓库地址写错，或仓库尚未在 GitHub 上创建\n"
            "       2) 浏览器授权未完成 / 账号无权写入该仓库\n"
            "       3) 远程有本地没有的提交且未变基成功\n"
            f"      可手动排查： git remote -v ; git fetch {remote} ; git status")

    ok("推送成功！")
    print()
    web_url = repo_url[:-4] if repo_url.endswith(".git") else repo_url
    print(f"仓库地址：{web_url}")
    rc, log = run(["git", "log", "--oneline", "-n", "5"])
    print(log.strip())
    print()
    info("后续每次改动：")
    print("        git add -A")
    print('        git commit -m "feat(m2): ..."')
    print("        git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
