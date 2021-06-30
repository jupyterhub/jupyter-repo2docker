import errno
import pytest
from tempfile import TemporaryDirectory
from unittest.mock import patch

import docker
import escapism

from repo2docker.app import Repo2Docker
from repo2docker.__main__ import make_r2d
from repo2docker.utils import chdir


def test_find_image():
    images = [{"RepoTags": ["some-org/some-repo:latest"]}]

    with patch("repo2docker.app.docker.APIClient") as FakeDockerClient:
        instance = FakeDockerClient.return_value
        instance.images.return_value = images

        r2d = Repo2Docker()
        r2d.output_image_spec = "some-org/some-repo"
        assert r2d.find_image()

        instance.images.assert_called_with()


def test_dont_find_image():
    images = [{"RepoTags": ["some-org/some-image-name:latest"]}]

    with patch("repo2docker.app.docker.APIClient") as FakeDockerClient:
        instance = FakeDockerClient.return_value
        instance.images.return_value = images

        r2d = Repo2Docker()
        r2d.output_image_spec = "some-org/some-other-image-name"
        assert not r2d.find_image()

        instance.images.assert_called_with()


def test_find_image_revision():
    images = [{"RepoTags": ["some-org/some-repoSomeHash:latest"]}]

    with patch("repo2docker.app.docker.APIClient") as FakeDockerClient:
        instance = FakeDockerClient.return_value
        instance.images.return_value = images

        r2d = Repo2Docker()
        r2d.output_image_spec = "some-org/some-repo"
        revision = True
        assert r2d.find_image(revision)

        instance.images.assert_called_with()


def test_dont_find_image_revision():
    images = [{"RepoTags": ["some-org/some-image-name:latest"]}]

    with patch("repo2docker.app.docker.APIClient") as FakeDockerClient:
        instance = FakeDockerClient.return_value
        instance.images.return_value = images

        r2d = Repo2Docker()
        r2d.output_image_spec = "some-org/some-other-image-name"
        revision = True
        assert not r2d.find_image(revision)

        instance.images.assert_called_with()


def test_image_name_remains_unchanged():
    # if we specify an image name, it should remain unmodified
    with TemporaryDirectory() as src:
        app = Repo2Docker()
        argv = ["--image-name", "a-special-name", "--no-build", src]
        app = make_r2d(argv)

        app.start()

        assert app.output_image_spec == "a-special-name"


def test_image_name_contains_sha1(repo_with_content):
    upstream, sha1 = repo_with_content
    app = Repo2Docker()
    # force selection of the git content provider by prefixing path with
    # file://. This is important as the Local content provider does not
    # store the SHA1 in the repo spec
    argv = ["--no-build", "file://" + upstream]
    app = make_r2d(argv)

    app.start()

    assert app.output_image_spec.endswith(sha1[:7])


def test_local_dir_image_name(repo_with_content):
    upstream, sha1 = repo_with_content
    app = Repo2Docker()
    argv = ["--no-build", upstream]
    app = make_r2d(argv)

    app.start()

    assert app.output_image_spec.startswith(
        "r2d" + escapism.escape(upstream, escape_char="-").lower()
    )


def test_build_kwargs(repo_with_content):
    upstream, sha1 = repo_with_content
    argv = [upstream]
    app = make_r2d(argv)
    app.extra_build_kwargs = {"somekey": "somevalue"}

    with patch.object(docker.APIClient, "build") as builds:
        builds.return_value = []
        app.build()
    builds.assert_called_once()
    args, kwargs = builds.call_args
    assert "somekey" in kwargs
    assert kwargs["somekey"] == "somevalue"


def test_run_kwargs(repo_with_content):
    upstream, sha1 = repo_with_content
    argv = [upstream]
    app = make_r2d(argv)
    app.extra_run_kwargs = {"somekey": "somevalue"}

    with patch.object(docker.DockerClient, "containers") as containers:
        app.start_container()
    containers.run.assert_called_once()
    args, kwargs = containers.run.call_args
    assert "somekey" in kwargs
    assert kwargs["somekey"] == "somevalue"


def test_root_not_allowed():
    with TemporaryDirectory() as src, patch("os.geteuid") as geteuid:
        geteuid.return_value = 0
        argv = [src]
        with pytest.raises(SystemExit) as exc:
            app = make_r2d(argv)
            assert exc.code == 1

        with pytest.raises(ValueError):
            app = Repo2Docker(repo=src, run=False)
            app.build()

        app = Repo2Docker(repo=src, user_id=1000, user_name="jovyan", run=False)
        app.initialize()
        with patch.object(docker.APIClient, "build") as builds:
            builds.return_value = []
            app.build()
        builds.assert_called_once()


def test_dryrun_works_without_docker(tmpdir, capsys):
    with chdir(tmpdir):
        with patch.object(docker, "APIClient") as client:
            client.side_effect = docker.errors.DockerException("Error: no Docker")
            app = Repo2Docker(dry_run=True)
            app.build()
            captured = capsys.readouterr()
            assert "Error: no Docker" not in captured.err


def test_error_log_without_docker(tmpdir, capsys):
    with chdir(tmpdir):
        with patch.object(docker, "APIClient") as client:
            client.side_effect = docker.errors.DockerException("Error: no Docker")
            app = Repo2Docker()

            with pytest.raises(SystemExit):
                app.build()
                captured = capsys.readouterr()
                assert "Error: no Docker" in captured.err
