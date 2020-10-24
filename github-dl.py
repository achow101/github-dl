#! /usr/bin/env python3

import argparse
import json
import os
import requests

from git import (
    InvalidGitRepositoryError,
    NoSuchPathError,
    Repo,
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

    # Prepare GitHub API headers
    headers = {
        "accept": "application/vnd.github.v3+json",
        "Authorization": f"token {args.token}",
    }

    # Make the directory everything gets downloaded into
    dl_dir = os.path.abspath(args.dl_dir)
    target_dir = os.path.join(dl_dir, args.owner, args.repo)
    os.makedirs(target_dir, exist_ok=True)

    # Make or update the git repo
    repo_path = os.path.join(target_dir, "repo")
    try:
        gh_repo = Repo(repo_path)
    except (InvalidGitRepositoryError, NoSuchPathError) as e:
        repo_url = f"https://{args.tokenuser}:{args.token}@github.com/{args.owner}/{args.repo}.git"
        gh_repo = Repo.clone_from(repo_url, repo_path)

    # Get git repo info
    r = requests.get(
        f"https://api.github.com/repos/{args.owner}/{args.repo}", headers=headers
    )
    repo_data = r.json()

    # Make the issues directory
    issues_dir = os.path.join(target_dir, "issues")
    os.makedirs(issues_dir, exist_ok=True)

    # Get all of the issues
    i = 1
    while True:
        r = requests.get(
            f"https://api.github.com/repos/{args.owner}/{args.repo}/issues?per_page&page={i}",
            headers=headers,
        )
        issues = r.json()
        if len(issues) == 0:
            break

        for issue in issues:
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
                r = requests.get(
                    f"{comments_url}?per_page=100&page={j}", headers=headers
                )
                comments = r.json()
                if len(comments) == 0:
                    break

                for comment in comments:
                    comment_file = os.path.join(issue_dir, str(comment["id"]))

                    with open(comment_file, "w") as f:
                        json.dump(comment, f, indent=4)

                j += 1

        i += 1


if __name__ == "__main__":
    main()
