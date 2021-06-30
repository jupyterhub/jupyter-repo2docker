import os
import json
import docker
import re
from ..base import BuildPack
from ... import app


class TarballBuildPack(BuildPack):
    """Tarball BuildPack"""

    image_file = "image.tar"

    def detect(self):
        """Check if current repo should be built with the Tarball BuildPack"""
        return os.path.exists(self.binder_path(self.image_file))

    def render(self):
        """Render the Dockerfile using by reading it from the source repo"""
        return "Found tarball {}\n".format(
            os.path.realpath(self.binder_path(self.image_file))
        )

    def build(
        self,
        client,
        image_spec,
        memory_limit,
        build_args,
        cache_from,
        extra_build_kwargs,
    ):

        self.log.debug(
            "Loading image from {}".format(self.image_file), extra=dict(phase="loading")
        )

        with open(self.binder_path(self.image_file), "rb") as f:
            result = [line for line in client.load_image(f, quiet=False)]
            if "error" in str(result):
                self.log.error(result, extra=dict(phase="failed"))
                raise docker.errors.ImageLoadError(result)

            if "Loaded image" in str(result):
                line = result[0]["stream"]
                image_tag = line.replace("Loaded image:", "").strip()
                self.log.debug(
                    "Successfully loaded {}".format(image_tag),
                    extra=dict(phase="loading"),
                )

                image_metadata = client.inspect_image(image_tag)
                image_r2d_version = image_metadata["Config"]["Labels"][
                    "repo2docker.version"
                ]
                if image_r2d_version != app.Repo2Docker.version:
                    self.log.warning(
                        "repo2docker version missmatch: image label has '{}' but running '{}'".format(
                            image_metadata["Config"]["Labels"]["repo2docker.version"],
                            app.Repo2Docker.version,
                        )
                    )

                return [{"image": image_tag}]
