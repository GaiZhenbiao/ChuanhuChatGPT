# -*- coding:utf-8 -*-
import os
import sys
import subprocess
from functools import lru_cache
import logging
import gradio as gr
import datetime
import platform

# This file is mainly used to describe repo version info, execute the git command, python pip command, shell command, etc.
# Part of the code in this file is referenced from stable-diffusion-webui/modules/launch_utils.py

python = sys.executable
pip = os.environ.get("PIP", "pip")
git = os.environ.get("GIT", "git")

# Pypi index url
index_url = os.environ.get("INDEX_URL", "")

# Whether to default to printing command output
default_command_live = True


def run(
    command, desc=None, errdesc=None, custom_env=None, live: bool = default_command_live
) -> str:
    if desc is not None:
        print(desc)
    run_kwargs = {
        "args": command,
        "shell": True,
        "env": os.environ if custom_env is None else custom_env,
        "encoding": "utf8",
        "errors": "ignore",
    }

    if not live:
        run_kwargs["stdout"] = run_kwargs["stderr"] = subprocess.PIPE

    result = subprocess.run(**run_kwargs)
    if result.returncode != 0:
        error_bits = [
            f"{errdesc or 'Error running command'}.",
            f"Command: {command}",
            f"Error code: {result.returncode}",
        ]
        if result.stdout:
            error_bits.append(f"stdout: {result.stdout}")
        if result.stderr:
            error_bits.append(f"stderr: {result.stderr}")
        raise RuntimeError("\n".join(error_bits))

    return result.stdout or ""


def run_pip(command, desc=None, pref=None, live=default_command_live):
    # if args.skip_install:
    #     return

    index_url_line = f" --index-url {index_url}" if index_url != "" else ""
    return run(
        f'"{python}" -m pip {command} --prefer-binary{index_url_line}',
        desc=f"{pref} Installing {desc}...",
        errdesc=f"Couldn't install {desc}",
        live=live,
    )


@lru_cache()
def commit_hash():
    try:
        return subprocess.check_output(
            [git, "rev-parse", "HEAD"], shell=False, encoding="utf8"
        ).strip()
    except Exception:
        return "<none>"


def commit_html():
    commit = commit_hash()
    if commit != "<none>":
        short_commit = commit[0:7]
        commit_info = f'<a style="text-decoration:none;color:inherit" href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/commit/{short_commit}">{short_commit}</a>'
    else:
        commit_info = "unknown \U0001F615"
    return commit_info


@lru_cache()
def tag_html():
    try:
        latest_tag = run(f"{git} describe --tags --abbrev=0", live=False).strip()
        try:
            # tag = subprocess.check_output([git, "describe", "--tags", "--exact-match"], shell=False, encoding='utf8').strip()
            tag = run(f"{git} describe --tags --exact-match", live=False).strip()
        except Exception:
            tag = "<edited>"
    except Exception:
        tag = "<none>"

    if tag == "<none>":
        tag_info = "unknown \U0001F615"
    elif tag == "<edited>":
        tag_info = f'<a style="text-decoration:none;color:inherit" href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/releases/tag/{latest_tag}">{latest_tag}</a><span style="font-size:smaller">*</span>'
    else:
        tag_info = f'<a style="text-decoration:none;color:inherit" href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/releases/tag/{tag}">{tag}</a>'

    return tag_info


def repo_tag_html():
    commit_version = commit_html()
    tag_version = tag_html()
    return tag_version if tag_version != "unknown \U0001F615" else commit_version


def versions_html():
    python_version = ".".join([str(x) for x in sys.version_info[0:3]])
    repo_version = repo_tag_html()
    return f"""
        Python: <span title="{sys.version}">{python_version}</span>
         • 
        Gradio: {gr.__version__}
         • 
        <a style="text-decoration:none;color:inherit" href="https://github.com/GaiZhenbiao/ChuanhuChatGPT">ChuanhuChat</a>: {repo_version}
        """


def version_time():
    git = "git"
    cmd = f"{git} log -1 --format=%cd --date=iso-strict"
    commit_time = "unknown"
    try:
        if platform.system() == "Windows":
            # For Windows
            env = dict(os.environ)  # copy the current environment
            env["TZ"] = "UTC"  # set timezone to UTC
            raw_commit_time = subprocess.check_output(
                cmd, shell=True, encoding="utf8", env=env
            ).strip()
        else:
            # For Unix systems
            cmd = f"TZ=UTC {cmd}"
            raw_commit_time = subprocess.check_output(
                cmd, shell=True, encoding="utf8"
            ).strip()

        # Convert the date-time to the desired format
        commit_datetime = datetime.datetime.strptime(
            raw_commit_time, "%Y-%m-%dT%H:%M:%S%z"
        )
        commit_time = commit_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

        # logging.info(f"commit time: {commit_time}")
    except Exception:
        commit_time = "unknown"
    return commit_time


def get_current_branch():
    try:
        # branch = run(f"{git} rev-parse --abbrev-ref HEAD").strip()
        branch = subprocess.check_output(
            [git, "rev-parse", "--abbrev-ref", "HEAD"], shell=False, encoding="utf8"
        ).strip()
    except Exception:
        branch = "<none>"
    return branch


def get_latest_release():
    try:
        import requests

        release = requests.get(
            "https://api.github.com/repos/GaiZhenbiao/ChuanhuChatGPT/releases/latest"
        ).json()
        tag = release["tag_name"]
        release_note = release["body"]
        need_pip = release_note.find("requirements reinstall needed") != -1
    except Exception:
        tag = "<none>"
        release_note = ""
        need_pip = False
    return {"tag": tag, "release_note": release_note, "need_pip": need_pip}


def get_tag_commit_hash(tag):
    try:
        import requests

        tags = requests.get(
            "https://api.github.com/repos/GaiZhenbiao/ChuanhuChatGPT/tags"
        ).json()
        commit_hash = [x["commit"]["sha"] for x in tags if x["name"] == tag][0]
    except Exception:
        commit_hash = "<none>"
    return commit_hash


def repo_need_stash():
    try:
        return (
            subprocess.check_output(
                [git, "diff-index", "--quiet", "HEAD", "--"],
                shell=False,
                encoding="utf8",
            ).strip()
            != ""
        )
    except Exception:
        return True


def background_update():
    # {git} fetch --all && ({git} pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f || ({git} stash && {git} pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f && {git} stash pop)) && {pip} install -r requirements.txt")
    try:
        latest_release = get_latest_release()
        latest_release_tag = latest_release["tag"]
        latest_release_hash = get_tag_commit_hash(latest_release_tag)
        need_pip = latest_release["need_pip"]
        need_stash = repo_need_stash()

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        current_branch = get_current_branch()
        updater_branch = f"tmp_{timestamp}"
        backup_branch = f"backup_{timestamp}"
        track_repo = "https://github.com/GaiZhenbiao/ChuanhuChatGPT.git"
        try:
            try:
                run(
                    f"{git} fetch {track_repo}",
                    desc="[Updater] Fetching from github...",
                    live=False,
                )
            except Exception:
                logging.error(
                    f"Update failed in fetching, check your network connection"
                )
                return "failed"

            run(
                f'{git} stash push --include-untracked -m "updater-{timestamp}"',
                desc=f"[Updater] Restoring you local changes on stash updater-{timestamp}",
                live=False,
            ) if need_stash else None

            run(f"{git} checkout -b {backup_branch}", live=False)
            run(f"{git} checkout -b {updater_branch}", live=False)
            run(f"{git} reset --hard FETCH_HEAD", live=False)
            run(
                f"{git} reset --hard {latest_release_hash}",
                desc=f"[Updater] Checking out {latest_release_tag}...",
                live=False,
            )
            run(f"{git} checkout {current_branch}", live=False)

            try:
                run(
                    f"{git} merge --no-edit {updater_branch} -q",
                    desc=f"[Updater] Trying to apply latest update on version {latest_release_tag}...",
                )
                run(f"{git} pull {track_repo} --tags", live=False)
            except Exception:
                logging.error(f"Update failed in merging")
                try:
                    run(
                        f"{git} merge --abort",
                        desc="[Updater] Conflict detected, canceling update...",
                    )
                    run(f"{git} reset --hard {backup_branch}", live=False)
                    run(f"{git} branch -D -f {updater_branch}", live=False)
                    run(f"{git} branch -D -f {backup_branch}", live=False)
                    run(f"{git} stash pop", live=False) if need_stash else None
                    logging.error(
                        f"Update failed, but your file was safely reset to the state before the update."
                    )
                    return "failed"
                except Exception as e:
                    logging.error(
                        f"!!!Update failed in resetting, try to reset your files manually. {e}"
                    )
                    return "failed"

            if need_stash:
                try:
                    run(
                        f"{git} stash apply",
                        desc="[Updater] Trying to restore your local modifications...",
                        live=False,
                    )
                except Exception:
                    run(
                        f"{git} reset --hard {backup_branch}",
                        desc="[Updater] Conflict detected, canceling update...",
                        live=False,
                    )
                    run(f"{git} branch -D -f {updater_branch}", live=False)
                    run(f"{git} branch -D -f {backup_branch}", live=False)
                    run(f"{git} stash pop", live=False)
                    logging.error(
                        f"Update failed in applying your local changes, but your file was safely reset to the state before the update."
                    )
                    return "failed"
                run(f"{git} stash drop", live=False)

            run(f"{git} branch -D -f {updater_branch}", live=False)
            run(f"{git} branch -D -f {backup_branch}", live=False)
        except Exception as e:
            logging.error(f"Update failed: {e}")
            return "failed"
        if need_pip:
            try:
                run_pip(
                    f"install -r requirements.txt",
                    pref="[Updater]",
                    desc="requirements",
                    live=False,
                )
            except Exception:
                logging.error(f"Update failed in pip install")
                return "failed"
        return "success"
    except Exception as e:
        logging.error(f"Update failed: {e}")
        return "failed"
