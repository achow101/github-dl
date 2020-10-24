#! /usr/bin/env python3

import argparse
import os

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


if __name__ == "__main__":
    main()
