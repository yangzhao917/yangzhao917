import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from requests import RequestException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_readme import (  # noqa: E402
    BonjourFetchError,
    GitHubFetchError,
    fetch_github_repos,
    parse_profile_description,
    render_readme,
)


class ProfileDescriptionTests(unittest.TestCase):
    def test_reads_visible_bonjour_bio_and_ignores_navigation_prompt(self):
        soup = BeautifulSoup(
            """
            <div data-profile-bio="true">
              🧑‍💻 独立开发者；
              <br>
              🏆 黑客松爱好者；
              <br>
              社交媒体｜作品案例 看下面👇
              <br>
              社交媒体｜作品案例｜获奖经历 看下面👇
            </div>
            """,
            "html.parser",
        )

        self.assertEqual(
            parse_profile_description(soup),
            ["🧑‍💻 独立开发者；", "🏆 黑客松爱好者；"],
        )

    def test_missing_profile_bio_is_not_replaced_with_static_copy(self):
        with self.assertRaises(BonjourFetchError):
            parse_profile_description(BeautifulSoup("<p>简介</p>", "html.parser"))


class GitHubDataTests(unittest.TestCase):
    CONFIG = {
        "sources": {"github_username": "yangzhao917"},
    }

    @patch("update_readme.requests.get", side_effect=RequestException("offline"))
    def test_github_failure_is_not_replaced_with_empty_works(self, _get):
        with self.assertRaises(GitHubFetchError):
            fetch_github_repos(self.CONFIG)

    @patch("update_readme.requests.get")
    def test_lists_all_live_repos_sorted_by_stars(self, get):
        response = Mock()
        response.json.return_value = [
            {"name": "new-work", "fork": False, "stargazers_count": 0, "description": None},
            {"name": "popular-work", "fork": False, "stargazers_count": 7, "description": "热门作品"},
            {"name": "another-work", "fork": False, "stargazers_count": 3, "description": " 另一个作品 "},
        ]
        get.return_value = response

        # 不做数量上限，也不做人工排除，全部实时仓库按 star 数排序展示，
        # 简介取自仓库实时描述并去除首尾空白。
        self.assertEqual(
            fetch_github_repos(self.CONFIG),
            [
                {"name": "popular-work", "stars": 7, "description": "热门作品"},
                {"name": "another-work", "stars": 3, "description": "另一个作品"},
                {"name": "new-work", "stars": 0, "description": ""},
            ],
        )

    @patch("update_readme.requests.get")
    def test_forked_repos_are_filtered(self, get):
        response = Mock()
        response.json.return_value = [
            {"name": "forked-work", "fork": True, "stargazers_count": 99, "description": "x"},
            {"name": "own-work", "fork": False, "stargazers_count": 1, "description": "自己的作品"},
        ]
        get.return_value = response

        self.assertEqual(
            fetch_github_repos(self.CONFIG),
            [{"name": "own-work", "stars": 1, "description": "自己的作品"}],
        )

    @patch("update_readme.requests.get")
    def test_no_eligible_work_fails_explicitly(self, get):
        response = Mock()
        response.json.return_value = [
            {"name": "forked-work", "fork": True, "stargazers_count": 99},
        ]
        get.return_value = response

        with self.assertRaises(GitHubFetchError):
            fetch_github_repos(self.CONFIG)

class RenderTests(unittest.TestCase):
    CONFIG = {
        "sources": {"github_username": "someone"},
        "static": {
            "story": "我是杨钊。",
            "name_en": "Zhao",
            "title": "独立开发者",
            "subtitle": "关注真实需求",
            "location": "上海",
            "xiaohongshu_url": "https://xhs.example",
            "bilibili_url": "https://bili.example",
            "bilibili_name": "是杨钊吖",
            "email": "yz0917@foxmail.com",
            "stats_instance": "stats.example",
        },
    }

    def test_work_without_description_has_no_dangling_separator(self):
        output = render_readme(
            self.CONFIG,
            {"profile_description": ["🧑‍💻 独立开发者；"]},
            [
                {"name": "with-desc", "stars": 2, "description": "有简介的作品"},
                {"name": "no-desc", "stars": 0, "description": ""},
            ],
        )

        self.assertIn("- [**with-desc**](https://github.com/someone/with-desc) ⭐2 — 有简介的作品", output)
        self.assertIn("- [**no-desc**](https://github.com/someone/no-desc)\n", output)


if __name__ == "__main__":
    unittest.main()
