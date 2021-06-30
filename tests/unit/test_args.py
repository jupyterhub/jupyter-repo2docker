"""
Test argument parsing and r2d construction
"""
import os
import pytest
from repo2docker.__main__ import make_r2d
from repo2docker import __version__


def test_version(capsys):
    """
    Test passing '--version' to repo2docker
    """
    with pytest.raises(SystemExit):
        make_r2d(["--version"])
    assert capsys.readouterr().out == "{}\n".format(__version__)


def test_simple():
    """
    Test simplest possible invocation to r2d
    """
    r2d = make_r2d(["."])
    assert r2d.repo == "."


def test_editable():
    """
    Test --editable behavior
    """
    r2d = make_r2d(["--editable", "."])
    assert r2d.repo == "."
    assert r2d.volumes[os.getcwd()] == "."


def test_dry_run():
    """
    Test passing --no-build implies --no-run and lack of --push
    """
    r2d = make_r2d(["--no-build", "."])
    assert r2d.dry_run
    assert not r2d.run
    assert not r2d.push


def test_mem_limit():
    """
    Test various ways of passing --build-memory-limit
    """
    r2d = make_r2d(["--build-memory-limit", "1024", "."])
    assert int(r2d.build_memory_limit) == 1024

    r2d = make_r2d(["--build-memory-limit", "3K", "."])
    assert int(r2d.build_memory_limit) == 1024 * 3


def test_run_required():
    """
    Test all the things that should fail if we pass in --no-run
    """
    # Can't use volumes without running
    with pytest.raises(SystemExit):
        make_r2d(["--no-run", "--editable", "."])

    # Can't publish all ports without running
    with pytest.raises(SystemExit):
        make_r2d(["--no-run", "-P", "."])

    # Can't publish any ports without running
    with pytest.raises(SystemExit):
        make_r2d(["--no-run", "-p", "8000:8000", "."])


def test_clean():
    """
    Test checkout is cleaned appropriately
    """

    # Don't clean when repo isn't local and we explicitly ask it to not clean
    assert not make_r2d(["--no-clean", "https://github.com/blah.git"]).cleanup_checkout
    # Do clean repo when repo isn't localj
    assert make_r2d(["https://github.com/blah.git"]).cleanup_checkout

    # Don't clean by default when repo exists locally
    assert not make_r2d(["."]).cleanup_checkout
    # Don't clean when repo exists locally and we explicitly ask it to not clean
    assert not make_r2d(["--no-clean", "."]).cleanup_checkout


def test_invalid_image_name():
    """
    Test validating image names
    """
    with pytest.raises(SystemExit):
        make_r2d(["--image-name", "_invalid", "."])
