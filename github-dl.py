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


class GitHubAPI:
    def __init__(self, user, token):
        self.user = user
        self.token = token

    # Helper function for api get requests
    def api_get(self, url, target_file=None, headers=None):
        if headers is None:
            headers = {
                "accept": "application/vnd.github.v3+json",
            }

        # Set Authorization header
        headers["Authorization"] = f"token {self.token}"

        LOG.debug(f"Get request to {url}")
        r = requests.get(url, headers=headers, stream=target_file is not None)

        # Check if we've been rate limited
        if not r.ok:
            r.close()
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
                    return api.api_get(url, target_file, headers)

        if target_file is not None:
            with open(target_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return None

        return r.json()

    # Make or update a git repo
    def get_repo(self, owner, repo, target_dir, dir_name):
        repo_path = os.path.join(target_dir, dir_name)
        try:
            gh_repo = Repo(repo_path)
        except (InvalidGitRepositoryError, NoSuchPathError) as e:
            LOG.info(f"Cloning {dir_name}")
            repo_url = f"https://{self.user}:{self.token}@github.com/{owner}/{repo}.git"
            gh_repo = Repo.clone_from(repo_url, repo_path, multi_options=["--mirror"])
        LOG.info(f"Updating {dir_name}")
        gh_remote = Remote(gh_repo, "origin")
        gh_remote.fetch()


def download_repo(args_dl_dir, api, owner, repo):
    # Make the directory everything gets downloaded into
    dl_dir = os.path.abspath(args_dl_dir)
    target_dir = os.path.join(dl_dir, owner, repo)
    os.makedirs(target_dir, exist_ok=True)

    # Fetch the repo info and write it to disk
    info_file = os.path.join(target_dir, "info")
    repo_info = api.api_get(f"https://api.github.com/repos/{owner}/{repo}")
    with open(info_file, "w") as f:
        json.dump(repo_info, f, indent=4)

    # Get the git repo
    api.get_repo(
        owner,
        repo,
        target_dir,
        "repo",
    )

    # Helper for making target dirs containin the data
    def make_subdir(name, parent_dir=target_dir):
        subdir_path = os.path.join(parent_dir, name)
        LOG.debug(f"Making subdirectory {subdir_path}")
        os.makedirs(subdir_path, exist_ok=True)
        return subdir_path

    # Helper for getting paginated api results
    def get_items(
        endpoint,
        id_field,
        filter_fn=None,
        item_fn=None,
        timestamp_field=None,
        custom_headers=None,
    ):
        LOG.info(f"Fetching {endpoint}")
        data_dir = make_subdir(endpoint)

        i = 1
        while True:
            LOG.info(f"Fetching {endpoint} page {i}")
            data = api.api_get(
                f"https://api.github.com/repos/{owner}/{repo}/{endpoint}?per_page=100&page={i}&state=all",
                None,
                custom_headers,
            )

            for item in data:
                # Skip PRs if we are doing issues
                if filter_fn is not None and not filter_fn(item):
                    continue

                num = item[id_field]
                if item_fn is not None:
                    # Make the directory for this item
                    item_dir = make_subdir(str(num), data_dir)

                    # Check whether this issue has any updates we don't have
                    item_file = os.path.join(item_dir, "item")
                    if timestamp_field is not None and os.path.isfile(item_file):
                        with open(item_file, "r") as f:
                            saved_item = json.load(f)
                        old = isoparse(saved_item[timestamp_field])
                        new = isoparse(item[timestamp_field])
                        if new <= old:
                            continue

                    # do per item processing
                    item_fn(item, item_dir, custom_headers)
                else:
                    # When theres is no per-item processing, there is no item dir, just a file
                    item_file = os.path.join(data_dir, str(num))

                # Write the item data
                with open(item_file, "w") as f:
                    json.dump(item, f, indent=4)

            if len(data) < 100:
                break
            i += 1

    # Helper function to get issue and pr comments
    def get_comments(item, item_dir, custom_headers):
        LOG.debug(f"Fetching comments for #{item['number']}")
        for field in ["comments_url", "review_comments_url"]:
            if field not in item:
                continue
            url = item[field]
            j = 1
            while True:
                comments = api.api_get(
                    f"{url}?per_page=100&page={j}", None, custom_headers
                )

                for comment in comments:
                    comment_file = os.path.join(item_dir, str(comment["id"]))

                    with open(comment_file, "w") as f:
                        json.dump(comment, f, indent=4)

                if len(comments) < 100:
                    break
                j += 1

    # Get all of the issues
    if repo_info["has_issues"]:
        get_items(
            "issues",
            "number",
            lambda item: "pull_request" not in item,
            get_comments,
            "updated_at",
        )

    # Get all of the PRs
    get_items("pulls", "number", None, get_comments, "updated_at")

    # Get the labels
    get_items("labels", "id")

    # Get the milstones
    get_items("milestones", "id")

    # Helper function to get release assets
    def get_assets(item, item_dir, custom_headers):
        LOG.debug(f"Fetching release assets for {item['name']}")
        for asset in item["assets"]:
            api.api_get(
                f"{asset['browser_download_url']}",
                os.path.join(item_dir, asset["name"]),
                custom_headers,
            )
            asset_file = os.path.join(item_dir, f"{asset['name']}.txt")
            with open(asset_file, "w") as f:
                json.dump(asset, f, indent=4)

    # Get the releases
    get_items("releases", "id", None, get_assets, "published_at")

    # Make or update the git repo
    if repo_info["has_wiki"]:
        api.get_repo(
            owner,
            f"{repo}.wiki.git",
            target_dir,
            "wiki",
        )


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
    parser.add_argument(
        "repo",
        help="The repository name to download. If not specified, download all of owner's repos",
        nargs="?",
        default=None,
    )

    args = parser.parse_args()

    # Set the log level
    LOG.setLevel(log_levels[args.loglevel.lower()])

    api = GitHubAPI(args.tokenuser, args.token)

    if args.repo is not None:
        download_repo(args.dl_dir, api, args.owner, args.repo)
    else:
        LOG.info(f"Downloading all repos for {args.owner}")
        # Download all of the repos under args.owner
        i = 0
        while True:
            repos = api.api_get(
                f"https://api.github.com/users/{args.owner}/repos?per_page=100&page={i}"
            )
            for repo in repos:
                LOG.info(f"Downloading {repo['name']}")
                download_repo(args.dl_dir, api, args.owner, repo["name"])

            if len(repos) < 100:
                break

            i += 1


if __name__ == "__main__":
    main()
