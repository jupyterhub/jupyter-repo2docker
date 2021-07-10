#!/usr/bin/env python3
"""
Update one or more packages in the conda environment.yml

Usage:

python update.py [package ...]

If no packages are specified updates all apart from python
"""

from bz2 import decompress
from collections import defaultdict
import json
import os
import pathlib
from packaging import version
import sys
from urllib.request import urlopen
from ruamel.yaml import YAML


HERE = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = HERE / "environment.yml"
NOARCH_REPODATA = "https://conda.anaconda.org/conda-forge/noarch/repodata.json.bz2"
LINUX64_REPODATA = "https://conda.anaconda.org/conda-forge/linux-64/repodata.json.bz2"
EXCLUDE_PACKAGES = ("python",)


yaml = YAML(typ="rt")


def update(dep_names):
    with open(ENV_FILE) as f:
        env = yaml.load(f)
    deps = env["dependencies"]
    if not dep_names:
        dep_names = [
            d.split("=")[0] for d in deps if d.split("=")[0] not in EXCLUDE_PACKAGES
        ]

    cf_packages = defaultdict(list)
    for url in (NOARCH_REPODATA, LINUX64_REPODATA):
        print(f"Loading {url}")
        with urlopen(url) as r:
            j = json.loads(decompress(r.read()))
        for pkg in j["packages"].values():
            cf_packages[pkg["name"]].append(version.parse(pkg["version"]))

    for n in range(len(deps)):
        name = deps[n].split("=")[0]
        if name in dep_names:
            latest = max(cf_packages[name]).base_version
            deps[n] = f"{name}={latest}"
            print(deps[n])

    with open(ENV_FILE, "w") as f:
        yaml.dump(env, f)


if __name__ == "__main__":
    update(sys.argv[1:])
