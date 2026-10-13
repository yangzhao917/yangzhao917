#!/usr/bin/env python3
"""Fetch data from multiple sources and regenerate README.md."""

import os
import sys
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yml"
TEMPLATE_DIR = ROOT / "templates"
README_PATH = ROOT / "README.md"

GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Bonjour.bio ──────────────────────────────────────────

class BonjourFetchError(RuntimeError):
    """Bonjour 是关于我内容的权威来源，无法安全读取时停止更新。"""


def fetch_bonjour_data(config):
    url = config["sources"]["bonjour_url"]
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        raise BonjourFetchError(f"Bonjour fetch failed: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    return {"profile_description": parse_profile_description(soup)}


def parse_profile_description(soup):
    """读取页面可见的个人简介，不使用被截断的 SEO 元数据。"""
    node = soup.select_one("[data-profile-bio]")
    if not node:
        raise BonjourFetchError("Bonjour profile description is missing")

    lines = [line.strip() for line in node.get_text("\n").splitlines() if line.strip()]
    # 导航提示行的文案会随页面改版变化（曾由“作品案例”改为“作品案例｜获奖经历”），
    # 因此按“看下面”标记识别并剔除，避免把导航提示当成个人简介发布。
    description = [line for line in lines if "看下面" not in line]
    if not description:
        raise BonjourFetchError("Bonjour profile description is empty")
    return description


# ── GitHub API ───────────────────────────────────────────

class GitHubFetchError(RuntimeError):
    """GitHub 作品数据无法安全读取时停止更新。"""


def fetch_github_repos(config):
    username = config["sources"]["github_username"]
    excluded = set(config["excluded_repos"])
    max_repos = config["max_featured_repos"]

    try:
        resp = requests.get(
            f"https://api.github.com/users/{username}/repos",
            params={"per_page": 100, "sort": "updated"},
            timeout=15,
        )
        resp.raise_for_status()
        all_repos = resp.json()
    except Exception as e:
        raise GitHubFetchError(f"GitHub API failed: {e}") from e

    if not isinstance(all_repos, list):
        raise GitHubFetchError("GitHub repository response is not a list")

    repos = []
    for r in all_repos:
        name = r["name"]
        if name in excluded or r["fork"]:
            continue
        repos.append({
            "name": name,
            "stars": r["stargazers_count"],
        })

    repos.sort(key=lambda x: x["stars"], reverse=True)
    featured_repos = repos[:max_repos]
    # 一个可用作品都没有时仍然失败：宁可停止更新，也不发布空的作品列表。
    if not featured_repos:
        raise GitHubFetchError("No eligible GitHub works found")

    return featured_repos


# ── Render ───────────────────────────────────────────────

def render_readme(config, bonjour, repos):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("README.md.j2")
    return template.render(
        static=config["static"],
        github_username=config["sources"]["github_username"],
        profile_description=bonjour["profile_description"],
        repos=repos,
    )


# ── Diff + Output ────────────────────────────────────────

def build_summary(old_text, new_text):
    parts = []
    old_lines = set(old_text.splitlines())
    new_lines = set(new_text.splitlines())
    added = new_lines - old_lines
    removed = old_lines - new_lines
    if added:
        parts.append(f"{len(added)} lines added")
    if removed:
        parts.append(f"{len(removed)} lines removed")
    return "; ".join(parts)


def set_output(key, value):
    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a") as f:
            f.write(f"{key}={value}\n")


def main():
    config = load_config()

    print("Fetching Bonjour.bio data...")
    try:
        bonjour = fetch_bonjour_data(config)
    except BonjourFetchError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Fetching GitHub repos...")
    try:
        repos = fetch_github_repos(config)
    except GitHubFetchError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Rendering README ({len(repos)} works)...")
    new_content = render_readme(config, bonjour, repos)

    old_content = ""
    if README_PATH.exists():
        old_content = README_PATH.read_text(encoding="utf-8")

    if new_content.strip() == old_content.strip():
        print("No changes detected.")
        set_output("changed", "false")
        return

    summary = build_summary(old_content, new_content)
    print(f"Changes detected: {summary}")
    README_PATH.write_text(new_content, encoding="utf-8")
    set_output("changed", "true")
    set_output("summary", summary)


if __name__ == "__main__":
    main()
