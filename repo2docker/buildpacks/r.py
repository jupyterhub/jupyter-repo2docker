import re
import os
import datetime
import requests

from distutils.version import LooseVersion as V

from .python import PythonBuildPack
from ._r_base import rstudio_base_scripts, DEVTOOLS_VERSION, IRKERNEL_VERSION


class RBuildPack(PythonBuildPack):
    """
    Setup R for use with a repository

    This sets up R + RStudio + IRKernel for a repository that contains:

    1. A `runtime.txt` file with the text:

       r-<year>-<month>-<date>

       Where 'year', 'month' and 'date' refer to a specific
       date snapshot of https://mran.microsoft.com/timemachine
       from which libraries are to be installed.

    2. A `DESCRIPTION` file signaling an R package

    If there is no `runtime.txt`, then the MRAN snapshot is set to latest
    date that is guaranteed to exist across timezones.

    Additional R packages are installed if specified either

    - in a file `install.R`, that will be executed at build time,
      and can be used for installing packages from both MRAN and GitHub

    - as dependencies in a `DESCRIPTION` file

    - are needed by a specific tool

    The `r-base` package from Ubuntu apt repositories is used to install
    R itself, rather than any of the methods from https://cran.r-project.org/.

    The `r-base-dev` package is installed as advised in RStudio instructions.
    """

    @property
    def runtime(self):
        """
        Return contents of runtime.txt if it exists, '' otherwise
        """
        if not hasattr(self, "_runtime"):
            runtime_path = self.binder_path("runtime.txt")
            try:
                with open(runtime_path) as f:
                    self._runtime = f.read().strip()
            except FileNotFoundError:
                self._runtime = ""

        return self._runtime

    @property
    def r_version(self):
        """Detect the R version for a given `runtime.txt`

        Will return the version specified by the user or the current default
        version.
        """
        version_map = {
            "3.4": "3.4",
            "3.5": "3.5.3-1bionic",
            "3.5.0": "3.5.0-1bionic",
            "3.5.1": "3.5.1-2bionic",
            "3.5.2": "3.5.2-1bionic",
            "3.5.3": "3.5.3-1bionic",
            "3.6": "3.6.1-3bionic",
            "3.6.0": "3.6.0-2bionic",
            "3.6.1": "3.6.1-3bionic",
            "4.0": "4.0.2-1.1804.0",
            "4.0.2": "4.0.2-1.1804.0",
        }
        # the default if nothing is specified
        r_version = "3.6"

        if not hasattr(self, "_r_version"):
            parts = self.runtime.split("-")
            if len(parts) == 5:
                r_version = parts[1]
                if r_version not in version_map:
                    raise ValueError(
                        "Version '{}' of R is not supported.".format(r_version)
                    )

            # translate to the full version string
            self._r_version = version_map.get(r_version)

        return self._r_version

    @property
    def checkpoint_date(self):
        """
        Return the date of MRAN checkpoint to use for this repo

        Returns '' if no date is specified
        """
        if not hasattr(self, "_checkpoint_date"):
            match = re.match(r"r-(\d.\d(.\d)?-)?(\d\d\d\d)-(\d\d)-(\d\d)", self.runtime)
            if not match:
                self._checkpoint_date = False
            else:
                # turn the last three groups of the match into a date
                self._checkpoint_date = datetime.date(
                    *[int(s) for s in match.groups()[-3:]]
                )

        return self._checkpoint_date

    def detect(self):
        """
        Check if current repo should be built with the R Build pack

        super().detect() is not called in this function - it would return
        false unless a `requirements.txt` is present and we do not want
        to require the presence of a `requirements.txt` to use R.
        """
        # If no date is found, then self.checkpoint_date will be False
        # Otherwise, it'll be a date object, which will evaluate to True
        if self.checkpoint_date:
            return True

        description_R = "DESCRIPTION"
        if not self.binder_dir and os.path.exists(description_R):
            if not self.checkpoint_date:
                # no R snapshot date set through runtime.txt
                # set the R runtime to the latest date that is guaranteed to
                # be on MRAN across timezones
                two_days_ago = datetime.date.today() - datetime.timedelta(days=2)
                self._checkpoint_date = self._get_latest_working_mran_date(
                    two_days_ago, 3
                )
                self._runtime = "r-{}".format(str(self._checkpoint_date))
            return True

    def get_path(self):
        """
        Return paths to be added to the PATH environment variable.

        The RStudio package installs its binaries in a non-standard path,
        so we explicitly add that path to PATH.
        """
        return super().get_path() + ["/usr/lib/rstudio-server/bin/"]

    def get_build_env(self):
        """
        Return environment variables to be set.

        We want libraries to be installed in a path that users can write to
        without needing root. This is set via the `R_LIBS_USER` environment
        variable, so we set that here.
        """
        return super().get_build_env() + [
            # This is the path where user libraries are installed
            ("R_LIBS_USER", "${APP_BASE}/rlibs")
        ]

    def get_packages(self):
        """
        Return list of packages to be installed.

        We install a base version of R, and packages required for RStudio to
        be installed.
        """
        packages = [
            # For rstudio
            "psmisc",
            "libapparmor1",
            "sudo",
            "lsb-release",
        ]
        # For R 3.4 we use the default Ubuntu package, for other versions we
        # install from a different PPA
        if V(self.r_version) < V("3.5"):
            packages.append("r-base")
            packages.append("r-base-dev")
            packages.append("libclang-dev")

        return super().get_packages().union(packages)

    def _get_latest_working_mran_date(self, startdate, max_prior):
        """
        Look for a working MRAN snapshot

        Starts from `startdate` and tries up to `max_prior` previous days.
        Raises `requests.HTTPError` with the last tried URL if no working snapshot found.
        """
        for days in range(max_prior + 1):
            test_date = startdate - datetime.timedelta(days=days)
            mran_url = "https://mran.microsoft.com/snapshot/{}".format(
                test_date.isoformat()
            )
            r = requests.head(mran_url)
            if r.ok:
                return test_date
            self.log.warning(
                "Failed to get MRAN snapshot URL %s: %s %s",
                mran_url,
                r.status_code,
                r.reason,
            )
        r.raise_for_status()

    def get_build_scripts(self):
        """
        Return series of build-steps common to all R repositories

        All scripts here should be independent of contents of the repository.

        This sets up:

        - A directory owned by non-root in ${R_LIBS_USER}
          for installing R packages into
        - RStudio
        - R's devtools package, at a particular frozen version
          (determined by MRAN)
        - IRKernel
        - nbrsessionproxy (to access RStudio via Jupyter Notebook)

        We set the snapshot date used to install R libraries from based on the
        contents of runtime.txt.
        """

        # TODO: decide date cutoff, use mran url before cutoff.

        # parse API resonse from packagemanger.rstudio.com mapping dates to
        # transaction_ids (= build ids) required for finaly repo url string
        timediffs = {
            x['transaction_id']:(
                datetime.datetime.strptime(
                    # unfortunately, some but time stamps come with microseconds - strip them via regex
                    re.search("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", x['date']).group(),
                    '%Y-%m-%dT%H:%M:%S'
                ) -
                datetime.datetime.strptime(self.checkpoint_date.isoformat(), '%Y-%m-%d')
            ).total_seconds()
            for x in requests.get('https://packagemanager.rstudio.com/__api__/repos/1/transaction-dates?_sort=date&_order=asc').json()
        }
        # build  the final repository url
        repo_url = "https://packagemanager.rstudio.com/all/__linux__/xenial/{transaction_id}".format(
            transaction_id=max(key for key in timediffs if timediffs[key] <= 0)
        )

        scripts = []
        # For R 3.4 we want to use the default Ubuntu package but otherwise
        # we use the packages from R's own repo
        if V(self.r_version) >= V("3.5"):
            if V(self.r_version) >= V("4"):
                vs = "40"
            else:
                vs = "35"
            scripts += [
                (
                    "root",
                    rf"""
                    echo "deb https://cloud.r-project.org/bin/linux/ubuntu bionic-cran{vs}/" > /etc/apt/sources.list.d/r-ubuntu.list
                    """,
                ),
                # Dont use apt-key directly, as gpg does not always respect *_proxy vars. This increase the chances
                # of being able to reach it from behind a firewall
                (
                    "root",
                    r"""
                    wget --quiet -O - 'https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xe298a3a825c0d65dfd57cbb651716619e084dab9' | apt-key add -
                    """,
                ),
                (
                    "root",
                    r"""
                    apt-get update && \
                    apt-get install --yes r-base={R_version} \
                         r-base-dev={R_version} \
                         r-recommended={R_version} \
                         libclang-dev && \
                    apt-get -qq purge && \
                    apt-get -qq clean && \
                    rm -rf /var/lib/apt/lists/*
                    """.format(
                        R_version=self.r_version
                    ),
                ),
            ]

        scripts.append(
            (
                "root",
                r"""
                mkdir -p ${R_LIBS_USER} && \
                chown -R ${NB_USER}:${NB_USER} ${R_LIBS_USER}
                """,
            )
        )
        scripts += rstudio_base_scripts()
        scripts += [
            (
                "root",
                # Set paths so that RStudio shares libraries with base R
                # install. This first comments out any R_LIBS_USER that
                # might be set in /etc/R/Renviron and then sets it.
                r"""
                sed -i -e '/^R_LIBS_USER=/s/^/#/' /etc/R/Renviron && \
                echo "R_LIBS_USER=${R_LIBS_USER}" >> /etc/R/Renviron
                """,
            ),
            (
                "${NB_USER}",
                # Install a pinned version of IRKernel and set it up for use!
                r"""
                R --quiet -e "install.packages('devtools', repos='https://mran.microsoft.com/snapshot/{devtools_version}', method='libcurl')" && \
                R --quiet -e "devtools::install_github('IRkernel/IRkernel', ref='{irkernel_version}')" && \
                R --quiet -e "IRkernel::installspec(prefix='$NB_PYTHON_PREFIX')"
                """.format(
                    devtools_version=DEVTOOLS_VERSION, irkernel_version=IRKERNEL_VERSION
                ),
            ),
            (
                "${NB_USER}",
                # Install shiny library
                r"""
                R --quiet -e "install.packages('shiny', repos='{}', method='libcurl')"
                """.format(
                    repo_url
                ),
            ),
            (
                "root",
                # We set the default CRAN repo to the MRAN one at given date
                # We set download method to be curl so we get HTTPS support
                r"""
                echo "options(repos = c(CRAN='{repo_url}'), download.file.method = 'libcurl')" > /etc/R/Rprofile.site
                """.format(
                    repo_url=repo_url
                ),
            ),
        ]

        return super().get_build_scripts() + scripts

    def get_preassemble_script_files(self):
        files = super().get_preassemble_script_files()
        installR_path = self.binder_path("install.R")
        if os.path.exists(installR_path):
            files[installR_path] = installR_path

        return files

    def get_preassemble_scripts(self):
        """Install contents of install.R

        Attempt to execute `install.R` before copying the contents of the
        repository. We speculate that most of the time we do not need access.
        In case this fails we re-run it after copying the repository contents.

        The advantage of executing it before copying is that minor edits to the
        repository content will not trigger a re-install making things faster.
        """
        scripts = []

        installR_path = self.binder_path("install.R")
        if os.path.exists(installR_path):
            scripts += [
                (
                    "${NB_USER}",
                    "Rscript %s && touch /tmp/.preassembled || true" % installR_path,
                )
            ]

        return super().get_preassemble_scripts() + scripts

    def get_assemble_scripts(self):
        """Install the dependencies of or the repository itself"""
        assemble_scripts = super().get_assemble_scripts()

        installR_path = self.binder_path("install.R")
        if os.path.exists(installR_path):
            assemble_scripts += [
                (
                    "${NB_USER}",
                    # only run install.R if the pre-assembly failed
                    "if [ ! -f /tmp/.preassembled ]; then Rscript {}; fi".format(
                        installR_path
                    ),
                )
            ]

        description_R = "DESCRIPTION"
        if not self.binder_dir and os.path.exists(description_R):
            assemble_scripts += [
                ("${NB_USER}", 'R --quiet -e "devtools::install_local(getwd())"')
            ]

        return assemble_scripts
