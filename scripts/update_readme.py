#!/usr/bin/env python3
"""Fetch data from multiple sources and regenerate README.md."""

import json
import os
import re
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


# ── SocialDataX (Xiaohongshu) ────────────────────────────

def fetch_xhs_data(config):
    api_key = os.environ.get("SOCIALDATAX_API_KEY")
    if not api_key:
        print("[WARN] SOCIALDATAX_API_KEY not set, skipping XHS data")
        return None

    base = config["sources"]["socialdatax_base_url"].rstrip("/")
    profile_url = config["sources"]["xiaohongshu_profile_url"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = requests.post(
            f"{base}/socialdatax/api/v1/xhs/user/info",
            headers=headers,
            json={"profile_url": profile_url},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "code" in data:
            print(f"[WARN] SocialDataX error: {data.get('message')}")
            return None
        return {
            "bio": data.get("bio", "").split("\n")[0].strip(),
            "follower_count": data.get("follower_count"),
            "name": data.get("name", ""),
        }
    except Exception as e:
        print(f"[WARN] SocialDataX request failed: {e}")
        return None


# ── Bonjour.bio ──────────────────────────────────────────

def fetch_bonjour_data(config):
    url = config["sources"]["bonjour_url"]
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] Bonjour fetch failed: {e}")
        return {"awards": [], "events": []}

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    awards = parse_awards(text)
    events = parse_events(text)
    return {"awards": awards, "events": events}


def parse_awards(text):
    awards = []
    # Match "2026 数字艺术黑客松｜最有爱奖🥇" or "2025 算网杯 AI Agent 大赛 | 三等奖"
    pattern = r"(20\d{2})\s+(.+?)[｜|]\s*(.+)"
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(pattern, line)
        if not m:
            continue
        year, event, prize = m.group(1), m.group(2).strip(), m.group(3).strip()
        # Only keep award-like entries, limit prize length to avoid garbage
        if len(prize) > 50:
            continue
        if any(kw in prize for kw in ["奖", "Award", "Prize"]):
            awards.append({"year": year, "event": event, "prize": prize})
    return awards


def parse_events(text):
    # Bonjour page text is too unstructured for reliable parsing.
    # Use curated list; update config or this list when events change.
    known_events = [
        "人民日报｜百城千县黑客松 · 普宁专场",
        "模法黑客松 S1 / S4（医保智能体开发专场）",
        "AI Hackathon Tour 高校联赛 · 浙大站 / 哈工大站 / 南京站",
        "江苏知识产权人工智能创新大赛",
        "IntuitionX 跨年黑客松、杭州环球黑客松、北京 PARTY NIGHTS 人工智能主题日",
        "十堰黑客松社区（发起人）",
    ]
    return known_events


# ── GitHub API ───────────────────────────────────────────

def fetch_github_repos(config):
    username = config["sources"]["github_username"]
    excluded = set(config.get("excluded_repos", []))
    max_repos = config.get("max_featured_repos", 6)

    try:
        resp = requests.get(
            f"https://api.github.com/users/{username}/repos",
            params={"per_page": 100, "sort": "updated"},
            timeout=15,
        )
        resp.raise_for_status()
        all_repos = resp.json()
    except Exception as e:
        print(f"[WARN] GitHub API failed: {e}")
        return []

    repos = []
    for r in all_repos:
        name = r["name"]
        if name in excluded or r.get("fork"):
            continue
        repos.append({
            "name": name,
            "description": (r.get("description") or "").replace("|", "\\|")[:100],
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language") or "",
        })

    repos.sort(key=lambda x: x["stars"], reverse=True)
    return repos[:max_repos]


def is_repo_accessible(username, name):
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{username}/{name}",
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return True


# ── Render ───────────────────────────────────────────────

def render_readme(config, xhs, bonjour, repos):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("README.md.j2")
    return template.render(
        static=config["static"],
        github_username=config["sources"]["github_username"],
        xhs=xhs,
        awards=bonjour.get("awards", []),
        events=bonjour.get("events", []),
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
    return "; ".join(parts) if parts else "Minor formatting changes"


def set_output(key, value):
    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a") as f:
            f.write(f"{key}={value}\n")


def main():
    config = load_config()

    print("Fetching XHS data via SocialDataX...")
    xhs = fetch_xhs_data(config)

    print("Fetching Bonjour.bio data...")
    bonjour = fetch_bonjour_data(config)

    print("Fetching GitHub repos...")
    repos = fetch_github_repos(config)

    print(f"Rendering README ({len(repos)} repos, {len(bonjour.get('awards', []))} awards)...")
    new_content = render_readme(config, xhs, bonjour, repos)

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
