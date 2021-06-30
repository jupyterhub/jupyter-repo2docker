"""
Test tarball loading and saving
"""

import os
import re
import docker
import pytest
import logging
from shutil import copy
from unittest.mock import MagicMock
from unittest.mock import patch

from repo2docker.utils import chdir
from repo2docker.app import Repo2Docker
from repo2docker.buildpacks import TarballBuildPack


def create_test_tarball():
    if not os.path.isfile("tests/tarball/node10/image.tar"):
        r2d = Repo2Docker(repo="tests/base/node10")
        r2d.build()

        client = docker.APIClient(version="auto")
        image = client.get_image(r2d.output_image_spec)
        with open("tests/tarball/node10/image.tar", "wb") as f:
            for chunk in image:
                f.write(chunk)


def test_image_loading_image_name():
    create_test_tarball()

    r2d = Repo2Docker(
        repo="tests/tarball/node10", run=False  # will not match image name/tag below
    )

    r2d.initialize()
    r2d.build()

    assert re.match("r2dtests-2fbase-2fnode(.*):latest", r2d.output_image_spec)


def test_detect():
    with chdir("tests/tarball/empty_tar"):
        assert TarballBuildPack().detect()


def test_detect_binderdir(tmpdir):
    os.makedirs(os.path.join(tmpdir, "binder"))
    copy("tests/tarball/empty_tar/image.tar", os.path.join(tmpdir, "binder/image.tar"))
    with chdir(tmpdir):
        assert TarballBuildPack().detect()


def test_image_loading_error():
    r2d = Repo2Docker(repo="tests/tarball/empty_tar", run=False)

    r2d.initialize()

    with pytest.raises(docker.errors.ImageLoadError, match=r".* no such file .*"):
        r2d.build()


def test_build_response():
    create_test_tarball()

    with chdir("tests/tarball/node10"):
        client = docker.APIClient(version="auto")

        result = TarballBuildPack().build(
            client, "whaterver-image", None, None, None, None
        )

        assert "image" in result[0]
        assert re.match("r2dtests-2fbase-2fnode(.*):latest", result[0]["image"])


def test_version_mismatch_warning(caplog):
    create_test_tarball()

    with chdir("tests/tarball/node10"):
        fake_log_value = {"stream": "Loaded image: r2dtestimage"}
        fake_client = MagicMock(spec=docker.APIClient)
        fake_client.load_image.return_value = iter([fake_log_value])
        fake_labels = {"Config": {"Labels": {"repo2docker.version": "1.17.42"}}}
        fake_client.inspect_image.return_value = fake_labels

        with caplog.at_level(logging.INFO):
            result = TarballBuildPack().build(
                fake_client, "will-be-ignored", None, None, None, None
            )

            assert "repo2docker version missmatch" in str(caplog.text)


def test_save_image(tmpdir):
    with chdir(tmpdir):
        fake_client = MagicMock(spec=docker.APIClient)
        fake_client.get_image.return_value = [
            "not".encode(),
            "an".encode(),
            "image".encode(),
        ]

        with patch.object(
            Repo2Docker, "docker_client", return_value=fake_client
        ) as mock_method:
            r2d = Repo2Docker(save=True)
            r2d.start()
            assert os.path.isfile("image.tar"), "image.tar file exists"

        os.makedirs(os.path.join(tmpdir, ".binder"))
        with patch.object(
            Repo2Docker, "docker_client", return_value=fake_client
        ) as mock_method:
            r2d = Repo2Docker(save=True)
            r2d.start()
            assert os.path.isfile(".binder/image.tar"), "binder/image.tar file exists"
