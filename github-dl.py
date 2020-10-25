#! /usr/bin/env python3

import argparse
import json
import os
import requests
import time

from datetime import (
    datetime,
    timezone,
)
from git import (
    InvalidGitRepositoryError,
    NoSuchPathError,
    Repo,
    Remote,
)


def main():
    parser = argparse.ArgumentParser(
        description="Download all GitHub repo data and metadata"
    )
    parser.add_argument(
        "--dl-dir",
        help="The directory which will contain all of the downloaded data. Otherwise it is downloaded into the current directory",
        default=".",
    )
    parser.add_argument("tokenuser", help="The username the auth token belongs to")
    parser.add_argument(
        "token",
        help="The username and Personal Access Token pair to authenticate with GitHub",
    )
    parser.add_argument(
        "owner", help="The GitHub user or organization that owns the repository"
    )
    parser.add_argument("repo", help="The repository name to download")

    args = parser.parse_args()

    # Set Authorization header
    headers = {
        "accept": "application/vnd.github.v3+json",
        "Authorization": f"token {args.token}",
    }

    def api_get(url):
        r = requests.get(url, headers=headers)

        # Check if we've been rate limited
        if not r.ok:
            if r.status_code == 403:
                if r.headers["x-ratelimit-remaining"] == "0":
                    # Sleep until the rate limit resets
                    end = datetime.fromtimestamp(
                        int(r.headers["x-ratelimit-reset"]), tz=timezone.utc
                    )
                    now = datetime.now(tz=timezone.utc)
                    time_to_sleep = (end - now).total_seconds()
                    print(f"Rate limited, sleeping for {time_to_sleep} seconds")
                    time.sleep(time_to_sleep)

        return r.json()

    # Make the directory everything gets downloaded into
    dl_dir = os.path.abspath(args.dl_dir)
    target_dir = os.path.join(dl_dir, args.owner, args.repo)
    os.makedirs(target_dir, exist_ok=True)

    # Make or update the git repo
    repo_path = os.path.join(target_dir, "repo")
    try:
        gh_repo = Repo(repo_path)
    except (InvalidGitRepositoryError, NoSuchPathError) as e:
        print("Cloning repo")
        repo_url = f"https://{args.tokenuser}:{args.token}@github.com/{args.owner}/{args.repo}.git"
        gh_repo = Repo.clone_from(repo_url, repo_path)
    print("Updating repo")
    gh_remote = Remote(gh_repo, "origin")
    gh_remote.fetch(update_head_ok=True)
    gh_remote.fetch("+refs/pull/*:refs/remotes/upstream-pull/*")
    gh_repo.git.reset("--hard", "@{u}")

    # Make the issues directory
    issues_dir = os.path.join(target_dir, "issues")
    os.makedirs(issues_dir, exist_ok=True)

    # Get all of the issues
    print("Fetching issues")
    i = 1
    while True:
        print(f"Fetching issues page {i}")
        issues = api_get(
            f"https://api.github.com/repos/{args.owner}/{args.repo}/issues?per_page=100&page={i}&state=all"
        )
        if len(issues) == 0:
            break

        for issue in issues:
            # Skip PRs, we'll handle them all later
            if "pull_request" in issue:
                continue

            # Make the directory for this issue
            issue_num = issue["number"]
            issue_dir = os.path.join(issues_dir, str(issue_num))
            os.makedirs(issue_dir, exist_ok=True)

            # Write the issue to the dir
            issue_file = os.path.join(issue_dir, "issue")
            with open(issue_file, "w") as f:
                json.dump(issue, f, indent=4)

            # Get the comments
            comments_url = issue["comments_url"]
            j = 0
            while True:
                comments = api_get(f"{comments_url}?per_page=100&page={j}")
                if len(comments) == 0:
                    break

                for comment in comments:
                    comment_file = os.path.join(issue_dir, str(comment["id"]))

                    with open(comment_file, "w") as f:
                        json.dump(comment, f, indent=4)

                j += 1

        i += 1

    # Make the PRs directory
    prs_dir = os.path.join(target_dir, "prs")
    os.makedirs(prs_dir, exist_ok=True)

    # Get all of the PRs
    print("Fetching pull requests")
    i = 1
    while True:
        print(f"Fetching pull requests page {i}")
        prs = api_get(
            f"https://api.github.com/repos/{args.owner}/{args.repo}/pulls?per_page=100&page={i}state=all"
        )
        if len(prs) == 0:
            break

        for pr in prs:
            # Make the directory for this issue
            pr_num = pr["number"]
            pr_dir = os.path.join(prs_dir, str(pr_num))
            os.makedirs(pr_dir, exist_ok=True)

            # Write the issue to the dir
            pr_file = os.path.join(pr_dir, "pr")
            with open(pr_file, "w") as f:
                json.dump(pr, f, indent=4)

            # Get the comments
            comments_url = pr["comments_url"]
            review_comments_url = pr["review_comments_url"]
            for url in [comments_url, review_comments_url]:
                j = 0
                while True:
                    comments = api_get(f"{url}?per_page=100&page={j}")
                    if len(comments) == 0:
                        break

                    for comment in comments:
                        comment_file = os.path.join(pr_dir, str(comment["id"]))

                        with open(comment_file, "w") as f:
                            json.dump(comment, f, indent=4)

                    j += 1

        i += 1


if __name__ == "__main__":
    main()
