"""BuildPack for conda environments"""
import os
import re
from collections.abc import Mapping

from ruamel.yaml import YAML

from ..base import BaseImage
from .._r_base import rstudio_base_scripts, IRKERNEL_VERSION
from ...utils import is_local_pip_requirement

# pattern for parsing conda dependency line
PYTHON_REGEX = re.compile(r"python\s*=+\s*([\d\.]*)")
R_REGEX = re.compile(r"r-base\s*=+\s*([\d\.]*)")
# current directory
HERE = os.path.dirname(os.path.abspath(__file__))


class CondaBuildPack(BaseImage):
    """A conda BuildPack.

    Uses miniconda since it is more lightweight than Anaconda.

    """

    # The kernel conda environment file, if any.
    # As an absolute path within the container.
    _kernel_environment_file = ""
    # extra pip requirements.txt for the kernel
    _kernel_requirements_file = ""

    # The notebook server environment file.
    # As an absolute path within the container.
    _nb_environment_file = ""
    # extra pip requirements.txt for the notebook env
    _nb_requirements_file = ""

    def get_build_env(self):
        """Return environment variables to be set.

        We set `CONDA_DIR` to the conda install directory and
        the `NB_PYTHON_PREFIX` to the location of the jupyter binary.

        """
        if not self._nb_environment_file:
            # get_build_script_files locates requirements/environment files,
            # populating the _nb_environment_file attribute and others.
            # FIXME: move file detection and initialization of those attributes to its own step?
            self.get_build_script_files()

        env = super().get_build_env() + [
            ("CONDA_DIR", "${APP_BASE}/conda"),
            ("NB_PYTHON_PREFIX", "${CONDA_DIR}/envs/notebook"),
            ("NB_ENVIRONMENT_FILE", self._nb_environment_file),
            ("MAMBA_ROOT_PREFIX", "${CONDA_DIR}"),
            ("MAMBA_EXE", "/tmp/bin/micromamba"),
        ]
        if self._nb_requirements_file:
            env.append(("NB_REQUIREMENTS_FILE", self._nb_requirements_file))

        if self._kernel_environment_file:
            # if kernel environment file is separate
            env.extend(
                [
                    ("KERNEL_PYTHON_PREFIX", "${CONDA_DIR}/envs/kernel"),
                    ("KERNEL_ENVIRONMENT_FILE", self._kernel_environment_file),
                ]
            )
            if self._kernel_requirements_file:
                env.append(("KERNEL_REQUIREMENTS_FILE", self._kernel_requirements_file))
        else:
            env.append(("KERNEL_PYTHON_PREFIX", "${NB_PYTHON_PREFIX}"))
        return env

    def get_env(self):
        """Make kernel env the default for `conda install`"""
        env = super().get_env() + [("CONDA_DEFAULT_ENV", "${KERNEL_PYTHON_PREFIX}")]
        return env

    def get_path(self):
        """Return paths (including conda environment path) to be added to
        the PATH environment variable.

        """
        path = super().get_path()
        path.insert(0, "${CONDA_DIR}/bin")
        if self.py2:
            path.insert(0, "${KERNEL_PYTHON_PREFIX}/bin")
        path.insert(0, "${NB_PYTHON_PREFIX}/bin")
        return path

    def get_build_scripts(self):
        """
        Return series of build-steps common to all Python 3 repositories.

        All scripts here should be independent of contents of the repository.

        This sets up through `install-base-env.bash` (found in this directory):

        - a directory for the conda environment and its ownership by the
          notebook user
        - a Python 3 interpreter for the conda environment
        - a Python 3 jupyter kernel
        - a frozen base set of requirements, including:
            - support for Jupyter widgets
            - support for JupyterLab
            - support for nteract

        """
        return super().get_build_scripts() + [
            (
                "root",
                r"""
                TIMEFORMAT='time: %3R' \
                bash -c 'time /tmp/install-base-env.bash' && \
                rm /tmp/install-base-env.bash /tmp/environment.yml
                """,
            )
        ]

    major_pythons = {"2": "2.7", "3": "3.7"}

    def get_build_script_files(self):
        """
        Dict of files to be copied to the container image for use in building.

        This is copied before the `build_scripts` & `assemble_scripts` are
        run, so can be executed from either of them.

        It's a dictionary where the key is the source file path in the host
        system, and the value is the destination file path inside the
        container image.

        This currently adds a frozen set of Python requirements to the dict
        of files.

        """
        files = {
            "conda/install-base-env.bash": "/tmp/install-base-env.bash",
            "conda/activate-conda.sh": "/etc/profile.d/activate-conda.sh",
        }
        py_version = self.python_version
        self.log.info("Building conda environment for python=%s" % py_version)
        # Select the frozen base environment based on Python version.
        # avoids expensive and possibly conflicting upgrades when changing
        # major Python versions during upgrade.
        # If no version is specified or no matching X.Y version is found,
        # the default base environment is used.
        frozen_name = "environment.lock"
        pip_frozen_name = "requirements.txt"
        if py_version:
            if self.py2:
                # python 2 goes in a different env
                files[
                    "conda/environment.py-2.7.lock"
                ] = self._kernel_environment_file = "/tmp/env/kernel-environment.lock"
                # additional pip requirements for kernel env
                if os.path.exists(os.path.join(HERE, "requirements.py-2.7.txt")):
                    files[
                        "conda/requirements.py-2.7.txt"
                    ] = (
                        self._kernel_requirements_file
                    ) = "/tmp/env/kernel-requirements.txt"
            else:
                py_frozen_name = f"environment.py-{py_version}.lock"
                if os.path.exists(os.path.join(HERE, py_frozen_name)):
                    frozen_name = py_frozen_name
                    pip_frozen_name = f"requirements.py-{py_version}.txt"
                if not frozen_name:
                    self.log.warning(f"No frozen env for {py_version}")
        files[
            "conda/" + frozen_name
        ] = self._nb_environment_file = "/tmp/env/environment.lock"

        # add requirements.txt, if present
        if os.path.exists(os.path.join(HERE, pip_frozen_name)):
            files[
                "conda/" + pip_frozen_name
            ] = self._nb_requirements_file = "/tmp/env/requirements.txt"

        files.update(super().get_build_script_files())
        return files

    _environment_yaml = None

    @property
    def environment_yaml(self):
        if self._environment_yaml is not None:
            return self._environment_yaml

        environment_yml = self.binder_path("environment.yml")
        if not os.path.exists(environment_yml):
            self._environment_yaml = {}
            return self._environment_yaml

        with open(environment_yml) as f:
            env = YAML().load(f)
            # check if the env file is empty, if so instantiate an empty dictionary.
            if env is None:
                env = {}
            # check if the env file provided a dict-like thing not a list or other data structure.
            if not isinstance(env, Mapping):
                raise TypeError(
                    "environment.yml should contain a dictionary. Got %r" % type(env)
                )
            self._environment_yaml = env

        return self._environment_yaml

    @property
    def _should_preassemble_env(self):
        """Check for local pip requirements in environment.yaml

        If there are any local references, e.g. `-e .`,
        stage the whole repo prior to installation.
        """
        dependencies = self.environment_yaml.get("dependencies", [])
        pip_requirements = None
        for dep in dependencies:
            if isinstance(dep, dict) and dep.get("pip"):
                pip_requirements = dep["pip"]
        if isinstance(pip_requirements, list):
            for line in pip_requirements:
                if is_local_pip_requirement(line):
                    return False
        return True

    @property
    def python_version(self):
        """Detect the Python version for a given `environment.yml`

        Will return 'x.y' if version is found (e.g '3.6'),
        or a Falsy empty string '' if not found.

        Version information below the minor level is dropped.
        """
        if not hasattr(self, "_python_version"):
            py_version = None
            env = self.environment_yaml
            for dep in env.get("dependencies", []):
                if not isinstance(dep, str):
                    continue
                match = PYTHON_REGEX.match(dep)
                if not match:
                    continue
                py_version = match.group(1)
                break

            # extract major.minor
            if py_version:
                if len(py_version) == 1:
                    self._python_version = self.major_pythons.get(py_version[0])
                else:
                    # return major.minor
                    self._python_version = ".".join(py_version.split(".")[:2])
            else:
                self._python_version = ""

        return self._python_version

    @property
    def r_version(self):
        """Detect the Python version for a given `environment.yml`

        Will return 'x.y' if version is found (e.g '3.6'),
        or a Falsy empty string '' if not found.

        """
        if not hasattr(self, "_r_version"):
            self._r_version = ""
            env = self.environment_yaml
            for dep in env.get("dependencies", []):
                if not isinstance(dep, str):
                    continue
                match = R_REGEX.match(dep)
                if not match:
                    continue
                self._r_version = match.group(1)
                break

        return self._r_version

    @property
    def uses_r(self):
        """Detect whether the user also installs R packages.

        Will return True when a package prefixed with 'r-' is being installed.
        """
        if not hasattr(self, "_uses_r"):
            deps = self.environment_yaml.get("dependencies", [])
            self._uses_r = False
            for dep in deps:
                if not isinstance(dep, str):
                    continue
                if dep.startswith("r-"):
                    self._uses_r = True
                    break

        return self._uses_r

    @property
    def py2(self):
        """Am I building a Python 2 kernel environment?"""
        return self.python_version and self.python_version.split(".")[0] == "2"

    def get_preassemble_script_files(self):
        """preassembly only requires environment.yml

        enables caching assembly result even when
        repo contents change
        """
        assemble_files = super().get_preassemble_script_files()
        if self._should_preassemble_env:
            environment_yml = self.binder_path("environment.yml")
            if os.path.exists(environment_yml):
                assemble_files[environment_yml] = environment_yml
        return assemble_files

    def get_env_scripts(self):
        """Return series of build-steps specific to this source repository."""
        scripts = []
        environment_yml = self.binder_path("environment.yml")
        env_prefix = "${KERNEL_PYTHON_PREFIX}" if self.py2 else "${NB_PYTHON_PREFIX}"
        if os.path.exists(environment_yml):
            scripts.append(
                (
                    "${NB_USER}",
                    r"""
                TIMEFORMAT='time: %3R' \
                bash -c 'time /tmp/bin/micromamba install -p {0} -f "{1}" && \
                # time /tmp/bin/micromamba clean --all -y && \
                /tmp/bin/micromamba list -p {0} \
                '
                """.format(
                        env_prefix, environment_yml
                    ),
                )
            )

        if self.uses_r:
            if self.r_version:
                r_pin = "=" + self.r_version
            else:
                r_pin = ""
            scripts.append(
                (
                    "${NB_USER}",
                    r"""
                /tmp/bin/micromamba install -p {0} r-base{1} r-irkernel={2} r-devtools -y && \
                #  /tmp/bin/micromamba clean --all -f -y && \
                /tmp/bin/micromamba list -p {0}
                """.format(
                        env_prefix, r_pin, IRKERNEL_VERSION
                    ),
                )
            )
            scripts += rstudio_base_scripts()
            scripts += [
                (
                    "root",
                    r"""
                    echo auth-none=1 >> /etc/rstudio/rserver.conf && \
                    echo auth-minimum-user-id=0 >> /etc/rstudio/rserver.conf && \
                    echo "rsession-which-r={0}/bin/R" >> /etc/rstudio/rserver.conf && \
                    echo www-frame-origin=same >> /etc/rstudio/rserver.conf
                    """.format(
                        env_prefix
                    ),
                ),
                (
                    "${NB_USER}",
                    # Install a pinned version of IRKernel and set it up for use!
                    r"""
                 R --quiet -e "IRkernel::installspec(prefix='{0}')"
                 """.format(
                        env_prefix
                    ),
                ),
            ]
        return scripts

    def get_preassemble_scripts(self):
        scripts = super().get_preassemble_scripts()
        if self._should_preassemble_env:
            scripts.extend(self.get_env_scripts())
        return scripts

    def get_assemble_scripts(self):
        scripts = super().get_assemble_scripts()
        if not self._should_preassemble_env:
            scripts.extend(self.get_env_scripts())
        return scripts

    def detect(self):
        """Check if current repo should be built with the Conda BuildPack."""
        return os.path.exists(self.binder_path("environment.yml")) and super().detect()
