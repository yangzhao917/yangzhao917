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
        "max_featured_repos": 1,
        "work_values": {"unfinished-work": "帮助用户完成一件事"},
    }

    @patch("update_readme.requests.get", side_effect=RequestException("offline"))
    def test_github_failure_is_not_replaced_with_empty_works(self, _get):
        with self.assertRaises(GitHubFetchError):
            fetch_github_repos(self.CONFIG)

    @patch("update_readme.requests.get")
    def test_missing_required_work_field_fails_explicitly(self, get):
        response = Mock()
        response.json.return_value = [{
            "name": "missing-value-work",
            "fork": False,
            "stargazers_count": 0,
        }]
        get.return_value = response

        with self.assertRaises(GitHubFetchError):
            fetch_github_repos(self.CONFIG)

if __name__ == "__main__":
    unittest.main()
