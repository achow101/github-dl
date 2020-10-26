# GitHub-DL: The GitHub Repo Full Downloader

Downloads an entire GitHub repository and it's metadata.

Included in the download:
* Git repo itself as a mirror repository
* All issues and issue comments
* All Pull Requests, PR comments, and PR commits
* Git repo for the Wiki
* Labels
* Milestones
* Releases and release assets

The downloaded data results in the following directory structure:
```
- <root>: Directory; Root directory, specified with --dl-dir, or current working directory
|- <owner>: Directory; GitHub repo owner name
 |- <repo>: Directory; Github repo name
  |- info: JSON file; Information about the repo
  |- issues: Directory; Contains all of the issues and their data
   |- <number>: Directory; Contains information about the issue with this number
    |- item: JSON file; Information about this issue
    |- <id>: JSON file; Information for the comment with this ID
   |- labels: Directory; Contains information about the labels
    |- <id>: JSON file; Information for the label with this ID
   |- milestones: Directory; Contains information about the milestones
    |- <id>: JSON file; Information for the milestone with this ID
   |- pulls: Directory; Contains all of the pull requests and their data
    |- <number>: Directory; Contains information about the pull request with this number
     |- item: JSON file; Information about this pull request
     |- <id>: JSON file; Information for the comment with this ID
   |- releases: Directory; Contains information about and assets for releases
    |- <id>: JSON file; Information about the release for this ID
    |- <asset>: File, multiple; Asset for this release
   |- repo: Directory; Git repository for this repo
   |- wiki: Directory; Git repository for the wiki
```

## Installation

GitHub-DL uses [Poetry](https://python-poetry.org/) for dependency and virtualenv management.
Python 3.8+ is required.
Outside of poetry, the dependencies can be installed with:

```
pip install requests GitPython python-dateutil
```

## Usage

```
usage: github-dl.py [-h] [-l {critical,error,warning,info,debug}] [-d DL_DIR] tokenuser token owner [repo]

Download all GitHub repo data and metadata

positional arguments:
  tokenuser             The username the auth token belongs to
  token                 The username and Personal Access Token pair to authenticate with GitHub
  owner                 The GitHub user or organization that owns the repository
  repo                  The repository name to download. If not specified, download all of owner's repos

optional arguments:
  -h, --help            show this help message and exit
  -l {critical,error,warning,info,debug}, --loglevel {critical,error,warning,info,debug}
                        Set the logging level
  -d DL_DIR, --dl-dir DL_DIR
                        The directory which will contain all of the downloaded data. Otherwise it is downloaded into the current directory
```

### Example.

```
./github-dl.py --dl-dir ghdl -l debug achow101 <token> bitcoin-core hwi
```

This will download the [bitcoin-core/hwi](https://github.com/bitcoin-core/hwi) repository to a directory named `ghdl` in the current directory.

## GitHub API

All metadata (i.e. not the repo, PR commits, nor the wiki) is fetched via the GitHub API.
GitHub-DL requires a GitHub Personal Access Token (PAT), provided as `token`.
The PAT allows a higher API rate limit and can be configured to allow access to private repos so that they can be downloaded as well.
For public repositories, it is not necessary to give the PAT any permissions.
For those repos, it is only used to access a higher rate limit.
PATs are tied to a user, so the username for that token needs to be provided too as `tokenuser`.

### Rate Limits

The GitHub API has a rate limit of 60 requests per hour for unauthenticated requests.
It has a rate limit of 5000 requests per hour for authenticated requests.
Because GitHub-DL requires the use of a PAT, requests will be authenticated, so the rate limit of 5000 requests per hour will apply.
For very active repositories, all of the data may not be downloaded in 5000 requests.
GitHub-DL will handle when the rate limit is reached and wait for it to be reset before continuing.
During this time, it may appear to be hanging, but it is actually just waiting for the rate limit to reset.

## Pull Request Commits

Since GitHub conveniently provides refs to the PR's commits in the Git repo itself, this is how GitHub-DL downloads those commits.
The remote ref `refs/pull/*` point to the head commit for each PR, as well as a merge commit if the PR is still open.

## Restoring The Git Repo

Both the Git and the wiki repo are cloned using `git clone --mirror` so they are bare repositories that can be cloned with

```
git clone <path to repo>
```

The Pull Request commits can then be added to that cloned repository using

```
git fetch origin "+refs/pull/*:refs/remotes/upstream-pull/*"
```

The Pull Requests will then be available at `upstream-pull/<number>/head`.
These can be checked out with

```
git checkout upstream-pull/<number/head
```

## License

GitHub-DL is released under the MIT license. See [LICENSE](LICENSE) for more information.
