"""repo2docker: convert git repositories into jupyter-suitable docker images

Images produced by repo2docker can be used with Jupyter notebooks standalone
or with BinderHub.

Usage:

    python -m repo2docker https://github.com/you/your-repo
"""
import json
import sys
import logging
import os
import getpass
import shutil
import tempfile
import time

import docker
from urllib.parse import urlparse
from docker.utils import kwargs_from_env
from docker.errors import DockerException
import escapism
from pythonjsonlogger import jsonlogger

from traitlets import Any, Dict, Int, List, Unicode, Bool, default
from traitlets.config import Application

from . import __version__
from .buildpacks import (
    CondaBuildPack,
    TarballBuildPack,
    DockerBuildPack,
    JuliaProjectTomlBuildPack,
    JuliaRequireBuildPack,
    LegacyBinderDockerBuildPack,
    NixBuildPack,
    PipfileBuildPack,
    PythonBuildPack,
    RBuildPack,
)
from . import contentproviders
from .utils import ByteSpecification, chdir


class Repo2Docker(Application):
    """An application for converting git repositories to docker images"""

    name = "jupyter-repo2docker"
    version = __version__
    description = __doc__

    @default("log_level")
    def _default_log_level(self):
        """The application's default log level"""
        return logging.INFO

    git_workdir = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""
        Working directory to use for check out of git repositories.

        The default is to use the system's temporary directory. Should be
        somewhere ephemeral, such as /tmp.
        """,
    )

    subdir = Unicode(
        "",
        config=True,
        help="""
        Subdirectory of the git repository to examine.

        Defaults to ''.
        """,
    )

    cache_from = List(
        [],
        config=True,
        help="""
        List of images to try & re-use cached image layers from.

        Docker only tries to re-use image layers from images built locally,
        not pulled from a registry. We can ask it to explicitly re-use layers
        from non-locally built images by through the 'cache_from' parameter.
        """,
    )

    buildpacks = List(
        [
            TarballBuildPack,
            LegacyBinderDockerBuildPack,
            DockerBuildPack,
            JuliaProjectTomlBuildPack,
            JuliaRequireBuildPack,
            NixBuildPack,
            RBuildPack,
            CondaBuildPack,
            PipfileBuildPack,
            PythonBuildPack,
        ],
        config=True,
        help="""
        Ordered list of BuildPacks to try when building a git repository.
        """,
    )

    extra_build_kwargs = Dict(
        {},
        help="""
        extra kwargs to limit CPU quota when building a docker image.
        Dictionary that allows the user to set the desired runtime flag
        to configure the amount of access to CPU resources your container has.
        Reference https://docs.docker.com/config/containers/resource_constraints/#cpu
        """,
        config=True,
    )

    extra_run_kwargs = Dict(
        {},
        help="""
        extra kwargs to limit CPU quota when running a docker image.
        Dictionary that allows the user to set the desired runtime flag
        to configure the amount of access to CPU resources your container has.
        Reference https://docs.docker.com/config/containers/resource_constraints/#cpu
        """,
        config=True,
    )

    default_buildpack = Any(
        PythonBuildPack,
        config=True,
        help="""
        The default build pack to use when no other buildpacks are found.
        """,
    )

    # Git is our content provider of last resort. This is to maintain the
    # old behaviour when git and local directories were the only supported
    # content providers. We can detect local directories from the path, but
    # detecting if something will successfully `git clone` is very hard if all
    # you can do is look at the path/URL to it.
    content_providers = List(
        [
            contentproviders.Local,
            contentproviders.Zenodo,
            contentproviders.Figshare,
            contentproviders.Dataverse,
            contentproviders.Hydroshare,
            contentproviders.Swhid,
            contentproviders.Mercurial,
            contentproviders.Git,
        ],
        config=True,
        help="""
        Ordered list by priority of ContentProviders to try in turn to fetch
        the contents specified by the user.
        """,
    )

    build_memory_limit = ByteSpecification(
        0,
        help="""
        Total memory that can be used by the docker image building process.

        Set to 0 for no limits.
        """,
        config=True,
    )

    volumes = Dict(
        {},
        help="""
        Volumes to mount when running the container.

        Only used when running, not during build process!

        Use a key-value pair, with the key being the volume source &
        value being the destination volume.

        Both source and destination can be relative. Source is resolved
        relative to the current working directory on the host, and
        destination is resolved relative to the working directory of the
        image - ($HOME by default)
        """,
        config=True,
    )

    user_id = Int(
        help="""
        UID of the user to create inside the built image.

        Should be a uid that is not currently used by anything in the image.
        Defaults to uid of currently running user, since that is the most
        common case when running r2d manually.

        Might not affect Dockerfile builds.
        """,
        config=True,
    )

    @default("user_id")
    def _user_id_default(self):
        """
        Default user_id to current running user.
        """
        return os.geteuid()

    user_name = Unicode(
        "jovyan",
        help="""
        Username of the user to create inside the built image.

        Should be a username that is not currently used by anything in the
        image, and should conform to the restrictions on user names for Linux.

        Defaults to username of currently running user, since that is the most
        common case when running repo2docker manually.
        """,
        config=True,
    )

    @default("user_name")
    def _user_name_default(self):
        """
        Default user_name to current running user.
        """
        return getpass.getuser()

    appendix = Unicode(
        config=True,
        help="""
        Appendix of Dockerfile commands to run at the end of the build.

        Can be used to customize the resulting image after all
        standard build steps finish.
        """,
    )

    json_logs = Bool(
        False,
        help="""
        Log output in structured JSON format.

        Useful when stdout is consumed by other tools
        """,
        config=True,
    )

    repo = Unicode(
        ".",
        help="""
        Specification of repository to build image for.

        Could be local path or git URL.
        """,
        config=True,
    )

    ref = Unicode(
        None,
        help="""
        Git ref that should be built.

        If repo is a git repository, this ref is checked out
        in a local clone before repository is built.
        """,
        config=True,
        allow_none=True,
    )

    swh_token = Unicode(
        None,
        help="""
        Token to use authenticated SWH API access.

        If unset, default to unauthenticated (limited) usage of the Software
        Heritage API.
        """,
        config=True,
        allow_none=True,
    )

    cleanup_checkout = Bool(
        False,
        help="""
        Delete source repository after building is done.

        Useful when repo2docker is doing the git cloning
        """,
        config=True,
    )

    output_image_spec = Unicode(
        "",
        help="""
        Docker Image name:tag to tag the built image with.

        Required parameter.
        """,
        config=True,
    )

    push = Bool(
        False,
        help="""
        Set to true to push docker image after building
        """,
        config=True,
    )

    run = Bool(
        False,
        help="""
        Run docker image after building
        """,
        config=True,
    )

    # FIXME: Refactor class to be able to do --no-build without needing
    #        deep support for it inside other code
    dry_run = Bool(
        False,
        help="""
        Do not actually build the docker image, just simulate it.
        """,
        config=True,
    )

    # FIXME: Refactor classes to separate build & run steps
    run_cmd = List(
        [],
        help="""
        Command to run when running the container

        When left empty, a jupyter notebook is run.
        """,
        config=True,
    )

    all_ports = Bool(
        False,
        help="""
        Publish all declared ports from container whiel running.

        Equivalent to -P option to docker run
        """,
        config=True,
    )

    ports = Dict(
        {},
        help="""
        Port mappings to establish when running the container.

        Equivalent to -p {key}:{value} options to docker run.
        {key} refers to port inside container, and {value}
        refers to port / host:port in the host
        """,
        config=True,
    )

    environment = List(
        [],
        help="""
        Environment variables to set when running the built image.

        Each item must be a string formatted as KEY=VALUE
        """,
        config=True,
    )

    target_repo_dir = Unicode(
        "",
        help="""
        Path inside the image where contents of the repositories are copied to,
        and where all the build operations (such as postBuild) happen.

        Defaults to ${HOME} if not set
        """,
        config=True,
    )

    save = Bool(
        False,
        config=True,
        help="""
        Save the image to a tarball after the build and before running.

        The used filename is 'image.tar' in the binder directory.
        """,
    )

    def fetch(self, url, ref, checkout_path):
        """Fetch the contents of `url` and place it in `checkout_path`.

        The `ref` parameter specifies what "version" of the contents should be
        fetched. In the case of a git repository `ref` is the SHA-1 of a commit.

        Iterate through possible content providers until a valid provider,
        based on URL, is found.
        """
        picked_content_provider = None
        for ContentProvider in self.content_providers:
            cp = ContentProvider()
            spec = cp.detect(url, ref=ref)
            if spec is not None:
                picked_content_provider = cp
                self.log.info(
                    "Picked {cp} content "
                    "provider.\n".format(cp=cp.__class__.__name__)
                )
                break

        if picked_content_provider is None:
            self.log.error(
                "No matching content provider found for " "{url}.".format(url=url)
            )

        swh_token = self.config.get("swh_token", self.swh_token)
        if swh_token and isinstance(picked_content_provider, contentproviders.Swhid):
            picked_content_provider.set_auth_token(swh_token)

        for log_line in picked_content_provider.fetch(
            spec, checkout_path, yield_output=self.json_logs
        ):
            self.log.info(log_line, extra=dict(phase="fetching"))

        if not self.output_image_spec:
            image_spec = "r2d" + self.repo
            # if we are building from a subdirectory include that in the
            # image name so we can tell builds from different sub-directories
            # apart.
            if self.subdir:
                image_spec += self.subdir
            if picked_content_provider.content_id is not None:
                image_spec += picked_content_provider.content_id
            else:
                image_spec += str(int(time.time()))
            self.output_image_spec = escapism.escape(
                image_spec, escape_char="-"
            ).lower()

    def json_excepthook(self, etype, evalue, traceback):
        """Called on an uncaught exception when using json logging

        Avoids non-JSON output on errors when using --json-logs
        """
        self.log.error(
            "Error during build: %s",
            evalue,
            exc_info=(etype, evalue, traceback),
            extra=dict(phase="failed"),
        )

    def docker_client(self):
        """Single place to create Docker API client to allow mocking"""
        client = docker.APIClient(version="auto", **kwargs_from_env())
        return client

    def initialize(self):
        """Init repo2docker configuration before start"""
        # FIXME: Remove this function, move it to setters / traitlet reactors
        if self.json_logs:
            # register JSON excepthook to avoid non-JSON output on errors
            sys.excepthook = self.json_excepthook
            # Need to reset existing handlers, or we repeat messages
            logHandler = logging.StreamHandler()
            formatter = jsonlogger.JsonFormatter()
            logHandler.setFormatter(formatter)
            self.log = logging.getLogger("repo2docker")
            self.log.handlers = []
            self.log.addHandler(logHandler)
            self.log.setLevel(self.log_level)
        else:
            # due to json logger stuff above,
            # our log messages include carriage returns, newlines, etc.
            # remove the additional newline from the stream handler
            self.log.handlers[0].terminator = ""
            # We don't want a [Repo2Docker] on all messages
            self.log.handlers[0].formatter = logging.Formatter(fmt="%(message)s")

        if self.dry_run and (self.run or self.push):
            raise ValueError("Cannot push or run image if we are not building it")

        if self.volumes and not self.run:
            raise ValueError("Cannot mount volumes if container is not run")

    def push_image(self):
        """Push docker image to registry"""
        client = self.docker_client()
        # Build a progress setup for each layer, and only emit per-layer
        # info every 1.5s
        progress_layers = {}
        layers = {}
        last_emit_time = time.time()
        for chunk in client.push(self.output_image_spec, stream=True):
            # each chunk can be one or more lines of json events
            # split lines here in case multiple are delivered at once
            for line in chunk.splitlines():
                line = line.decode("utf-8", errors="replace")
                try:
                    progress = json.loads(line)
                except Exception as e:
                    self.log.warning("Not a JSON progress line: %r", line)
                    continue
                if "error" in progress:
                    self.log.error(progress["error"], extra=dict(phase="failed"))
                    raise docker.errors.ImageLoadError(progress["error"])
                if "id" not in progress:
                    continue
                # deprecated truncated-progress data
                if "progressDetail" in progress and progress["progressDetail"]:
                    progress_layers[progress["id"]] = progress["progressDetail"]
                else:
                    progress_layers[progress["id"]] = progress["status"]
                # include full progress data for each layer in 'layers' data
                layers[progress["id"]] = progress
                if time.time() - last_emit_time > 1.5:
                    self.log.info(
                        "Pushing image\n",
                        extra=dict(
                            progress=progress_layers, layers=layers, phase="pushing"
                        ),
                    )
                    last_emit_time = time.time()
        self.log.info(
            "Successfully pushed {}".format(self.output_image_spec),
            extra=dict(phase="pushing"),
        )

    def save_image(self):
        """Save Docker image to file"""
        client = self.docker_client()

        with chdir(self.repo):
            filename = self.default_buildpack().binder_path("image.tar")
            self.log.info("Saving image to file {}\n".format(filename))

            image = client.get_image(self.output_image_spec)
            with open(filename, "wb") as f:
                for chunk in image:
                    f.write(chunk)

        self.log.info("Successfully saved image\n")

    def run_image(self):
        """Run docker container from built image

        and wait for it to finish.
        """
        container = self.start_container()
        self.wait_for_container(container)

    def start_container(self):
        """Start docker container from built image

        Returns running container
        """
        client = docker.from_env(version="auto")

        docker_host = os.environ.get("DOCKER_HOST")
        if docker_host:
            host_name = urlparse(docker_host).hostname
        else:
            host_name = "127.0.0.1"
        self.hostname = host_name

        if not self.run_cmd:
            port = str(self._get_free_port())
            self.port = port
            # To use the option --NotebookApp.custom_display_url
            # make sure the base-notebook image is updated:
            # docker pull jupyter/base-notebook
            run_cmd = [
                "jupyter",
                "notebook",
                "--ip",
                "0.0.0.0",
                "--port",
                port,
                "--NotebookApp.custom_display_url=http://{}:{}".format(host_name, port),
            ]
            ports = {"%s/tcp" % port: port}
        else:
            # run_cmd given by user, if port is also given then pass it on
            run_cmd = self.run_cmd
            if self.ports:
                ports = self.ports
            else:
                ports = {}
        # store ports on self so they can be retrieved in tests
        self.ports = ports

        container_volumes = {}
        if self.volumes:
            api_client = self.docker_client()
            image = api_client.inspect_image(self.output_image_spec)
            image_workdir = image["ContainerConfig"]["WorkingDir"]

            for k, v in self.volumes.items():
                container_volumes[os.path.abspath(k)] = {
                    "bind": v if v.startswith("/") else os.path.join(image_workdir, v),
                    "mode": "rw",
                }

        run_kwargs = dict(
            publish_all_ports=self.all_ports,
            ports=ports,
            detach=True,
            command=run_cmd,
            volumes=container_volumes,
            environment=self.environment,
        )

        run_kwargs.update(self.extra_run_kwargs)

        self.log.debug(
            "Running container with image {}\n".format(self.output_image_spec),
            extra=dict(phase="running"),
        )
        container = client.containers.run(self.output_image_spec, **run_kwargs)

        while container.status == "created":
            time.sleep(0.5)
            container.reload()

        return container

    def wait_for_container(self, container):
        """Wait for a container to finish

        Displaying logs while it's running
        """

        try:
            for line in container.logs(stream=True):
                self.log.info(line.decode("utf-8"), extra=dict(phase="running"))

        finally:
            container.reload()
            if container.status == "running":
                self.log.info("Stopping container...\n", extra=dict(phase="running"))
                container.kill()
            exit_code = container.attrs["State"]["ExitCode"]

            container.wait()

            self.log.info(
                "Container finished running.\n".upper(), extra=dict(phase="running")
            )
            # are there more logs? Let's send them back too
            late_logs = container.logs().decode("utf-8")
            for line in late_logs.split("\n"):
                self.log.info(line + "\n", extra=dict(phase="running"))

            container.remove()
            if exit_code:
                sys.exit(exit_code)

    def _get_free_port(self):
        """
        Hacky method to get a free random port on local host
        """
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def find_image(self):
        # if this is a dry run it is Ok for dockerd to be unreachable so we
        # always return False for dry runs.
        if self.dry_run:
            return False
        # check if we already have an image for this content
        client = self.docker_client()
        for image in client.images():
            if image["RepoTags"] is not None:
                for tag in image["RepoTags"]:
                    if tag == self.output_image_spec + ":latest":
                        return True
        return False

    def build(self):
        """
        Build docker image
        """
        # Check if r2d can connect to docker daemon
        if not self.dry_run:
            try:
                self.docker_client()
            except DockerException as e:
                self.log.error(
                    "\nDocker client initialization error: %s.\nCheck if docker is running on the host.\n",
                    e,
                )
                self.exit(1)

        # If the source to be executed is a directory, continue using the
        # directory. In the case of a local directory, it is used as both the
        # source and target. Reusing a local directory seems better than
        # making a copy of it as it might contain large files that would be
        # expensive to copy.
        if os.path.isdir(self.repo):
            checkout_path = self.repo
        else:
            if self.git_workdir is None:
                checkout_path = tempfile.mkdtemp(prefix="repo2docker")
            else:
                checkout_path = self.git_workdir

        try:
            self.fetch(self.repo, self.ref, checkout_path)

            if self.find_image():
                self.log.info(
                    "Reusing existing image ({}), not "
                    "building.".format(self.output_image_spec)
                )
                # no need to build, so skip to the end by `return`ing here
                # this will still execute the finally clause and let's us
                # avoid having to indent the build code by an extra level
                return

            if self.subdir:
                checkout_path = os.path.join(checkout_path, self.subdir)
                if not os.path.isdir(checkout_path):
                    self.log.error(
                        "Subdirectory %s does not exist",
                        self.subdir,
                        extra=dict(phase="failure"),
                    )
                    raise FileNotFoundError("Could not find {}".format(checkout_path))

            with chdir(checkout_path):
                for BP in self.buildpacks:
                    bp = BP()
                    if bp.detect():
                        picked_buildpack = bp
                        break
                else:
                    picked_buildpack = self.default_buildpack()

                picked_buildpack.appendix = self.appendix
                # Add metadata labels
                picked_buildpack.labels["repo2docker.version"] = self.version
                repo_label = "local" if os.path.isdir(self.repo) else self.repo
                picked_buildpack.labels["repo2docker.repo"] = repo_label
                picked_buildpack.labels["repo2docker.ref"] = self.ref

                if self.dry_run:
                    print(picked_buildpack.render())
                else:
                    self.log.debug(
                        picked_buildpack.render(), extra=dict(phase="building")
                    )
                    if self.user_id == 0:
                        raise ValueError(
                            "Root as the primary user in the image is not permitted."
                        )

                    build_args = {
                        "NB_USER": self.user_name,
                        "NB_UID": str(self.user_id),
                    }
                    if self.target_repo_dir:
                        build_args["REPO_DIR"] = self.target_repo_dir
                    self.log.info(
                        "Using %s builder\n",
                        bp.__class__.__name__,
                        extra=dict(phase="building"),
                    )

                    for l in picked_buildpack.build(
                        self.docker_client(),
                        self.output_image_spec,
                        self.build_memory_limit,
                        build_args,
                        self.cache_from,
                        self.extra_build_kwargs,
                    ):
                        if "stream" in l:
                            self.log.info(l["stream"], extra=dict(phase="building"))
                        elif "error" in l:
                            self.log.info(l["error"], extra=dict(phase="failure"))
                            raise docker.errors.BuildError(l["error"], build_log="")
                        elif "status" in l:
                            self.log.info(
                                "Fetching base image...\r", extra=dict(phase="building")
                            )
                        elif "image" in l:
                            self.output_image_spec = l["image"]
                        else:
                            self.log.info(json.dumps(l), extra=dict(phase="building"))

        finally:
            # Cleanup checkout if necessary
            if self.cleanup_checkout:
                shutil.rmtree(checkout_path, ignore_errors=True)

    def start(self):
        self.build()

        if self.push:
            self.push_image()

        if self.save:
            self.save_image()

        if self.run:
            self.run_image()
