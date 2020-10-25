#! /usr/bin/env python3

import argparse
import json
import logging
import os
import requests
import sys
import time

from datetime import (
    datetime,
    timezone,
)
from dateutil.parser import (
    isoparse,
)
from git import (
    InvalidGitRepositoryError,
    NoSuchPathError,
    Repo,
    Remote,
)


log_levels = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.StreamHandler(sys.stdout))


def main():
    parser = argparse.ArgumentParser(
        description="Download all GitHub repo data and metadata"
    )
    parser.add_argument(
        "-l",
        "--loglevel",
        help="Set the logging level",
        choices=log_levels.keys(),
        default="info",
    )
    parser.add_argument(
        "-d",
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

    # Set the log level
    LOG.setLevel(log_levels[args.loglevel.lower()])

    # Set Authorization header
    headers = {
        "accept": "application/vnd.github.v3+json",
        "Authorization": f"token {args.token}",
    }

    # Helper function for api get requests
    def api_get(url):
        LOG.debug(f"Get request to {url}")
        r = requests.get(url, headers=headers)

        # Check if we've been rate limited
        if not r.ok:
            LOG.debug(f"HTTP failure, status {r.status_code}")
            if r.status_code == 403:
                if r.headers["x-ratelimit-remaining"] == "0":
                    # Sleep until the rate limit resets
                    end = datetime.fromtimestamp(
                        int(r.headers["x-ratelimit-reset"]), tz=timezone.utc
                    )
                    now = datetime.now(tz=timezone.utc)
                    LOG.debug(
                        f"Rate limit: {r.headers['x-ratelimit-limit']}, Rate limit resets at {end.astimezone().isoformat()}"
                    )
                    time_to_sleep = int((end - now).total_seconds()) + 1
                    LOG.info(f"Rate limited, sleeping for {time_to_sleep} seconds")
                    time.sleep(time_to_sleep)
                    return api_get(url)

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
        LOG.info("Cloning repo")
        repo_url = f"https://{args.tokenuser}:{args.token}@github.com/{args.owner}/{args.repo}.git"
        gh_repo = Repo.clone_from(repo_url, repo_path)
    LOG.info("Updating repo")
    gh_remote = Remote(gh_repo, "origin")
    gh_remote.fetch(update_head_ok=True)
    gh_remote.fetch("+refs/pull/*:refs/remotes/upstream-pull/*")
    gh_repo.git.reset("--hard", "@{u}")

    # Helper for making target dirs containin the data
    def make_subdir(name):
        subdir_path = os.path.join(target_dir, name)
        os.makedirs(subdir_path, exist_ok=True)
        return subdir_path

    # Helper for getting issues and prs and their comments
    def get_comments(endpoint, data_dir, comment_fields):
        i = 1
        while True:
            LOG.info(f"Fetching {endpoint} page {i}")
            data = api_get(
                f"https://api.github.com/repos/{args.owner}/{args.repo}/{endpoint}?per_page=100&page={i}&state=all"
            )

            for item in data:
                # Skip PRs if we are doing issues
                if endpoint == "issues" and "pull_request" in item:
                    continue

                # Make the directory for this item
                num = item["number"]
                item_dir = os.path.join(data_dir, str(num))
                os.makedirs(item_dir, exist_ok=True)

                # Check whether this issue has any updates we don't have
                item_file = os.path.join(item_dir, "item")
                if os.path.isfile(item_file):
                    with open(item_file, "r") as f:
                        saved_item = json.load(f)
                    old = isoparse(saved_item["updated_at"])
                    new = isoparse(item["updated_at"])
                    if new <= old:
                        continue

                # Get the comments
                LOG.debug(f"Fetching comments for {endpoint} {num}")
                for field in comment_fields:
                    url = item[field]
                    j = 1
                    while True:
                        comments = api_get(f"{url}?per_page=100&page={j}")

                        for comment in comments:
                            comment_file = os.path.join(item_dir, str(comment["id"]))

                            with open(comment_file, "w") as f:
                                json.dump(comment, f, indent=4)

                        if len(comments) < 100:
                            break
                        j += 1

                # Write the item data
                with open(item_file, "w") as f:
                    json.dump(item, f, indent=4)

            if len(data) < 100:
                break
            i += 1

    # Get all of the issues
    LOG.info("Fetching issues")
    get_comments("issues", make_subdir("issues"), ["comments_url"])

    # Get all of the PRs
    LOG.info("Fetching pull requests")
    get_comments("pulls", make_subdir("prs"), ["comments_url", "review_comments_url"])

    # Helper function to get page of results only
    def get_items(endpoint, data_dir):
        i = 1
        while True:
            LOG.info(f"Fetching {endpoint} page {i}")
            data = api_get(
                f"https://api.github.com/repos/{args.owner}/{args.repo}/{endpoint}?per_page=100&page={i}&state=all"
            )

            for item in data:
                item_id = item["id"]
                item_file = os.path.join(data_dir, str(item_id))

                # Write the item data
                with open(item_file, "w") as f:
                    json.dump(item, f, indent=4)

            if len(data) < 100:
                break
            i += 1

    # Get the labels
    LOG.info("Fetching labels")
    get_items("labels", make_subdir("labels"))


if __name__ == "__main__":
    main()
