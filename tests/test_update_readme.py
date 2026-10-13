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
        "excluded_repos": [],
        "max_featured_repos": 2,
    }

    @patch("update_readme.requests.get", side_effect=RequestException("offline"))
    def test_github_failure_is_not_replaced_with_empty_works(self, _get):
        with self.assertRaises(GitHubFetchError):
            fetch_github_repos(self.CONFIG)

    @patch("update_readme.requests.get")
    def test_features_repos_by_stars_without_extra_config(self, get):
        response = Mock()
        response.json.return_value = [
            {"name": "new-work", "fork": False, "stargazers_count": 0},
            {"name": "popular-work", "fork": False, "stargazers_count": 7},
        ]
        get.return_value = response

        # 新仓库无需任何额外配置即可进入精选，且按 star 数排序。
        self.assertEqual(
            fetch_github_repos(self.CONFIG),
            [
                {"name": "popular-work", "stars": 7},
                {"name": "new-work", "stars": 0},
            ],
        )

    @patch("update_readme.requests.get")
    def test_excluded_and_forked_repos_are_filtered(self, get):
        response = Mock()
        response.json.return_value = [
            {"name": "excluded-work", "fork": False, "stargazers_count": 99},
            {"name": "forked-work", "fork": True, "stargazers_count": 99},
            {"name": "kept-work", "fork": False, "stargazers_count": 1},
        ]
        get.return_value = response

        config = {**self.CONFIG, "excluded_repos": ["excluded-work"]}
        self.assertEqual(
            fetch_github_repos(config),
            [{"name": "kept-work", "stars": 1}],
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

if __name__ == "__main__":
    unittest.main()
