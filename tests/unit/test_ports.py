"""
Test Port mappings work on running non-jupyter workflows
"""

import requests
import time
import os
import tempfile
import random
from getpass import getuser

import docker
import pytest

from repo2docker.app import Repo2Docker
from repo2docker.__main__ import make_r2d


def read_port_mapping_response(
    request, tmpdir, host=None, port="", all_ports=False, protocol=None
):
    """
    Deploy container and test if port mappings work as expected

    Args:
        request: pytest request fixture
        host: the host interface to bind to
        port: the random host port to bind to
        protocol: the protocol to use valid values /tcp or /udp
    """
    port_protocol = "8888"
    if protocol:
        port_protocol += protocol
    host_port = port
    if host:
        host_port = (host, port)
    else:
        host = "localhost"

    if port:
        ports = {port_protocol: host_port}
    else:
        ports = {}

    # run in an empty temporary directory
    td = tempfile.TemporaryDirectory()
    # cleanup at the end of the test
    request.addfinalizer(td.cleanup)
    tmpdir.chdir()

    username = getuser()
    tmpdir.mkdir("username")
    r2d = Repo2Docker(
        repo=str(tmpdir.mkdir("repo")),
        user_id=os.geteuid(),
        user_name=username,
        all_ports=all_ports,
        ports=ports,
        run=True,
        run_cmd=["python", "-m", "http.server", "8888"],
    )
    r2d.initialize()
    r2d.build()
    # create container
    container = r2d.start_container()

    # register cleanup first thing so we don't leave it lying around
    def _cleanup():
        container.reload()
        if container.status == "running":
            container.kill()
        try:
            container.remove()
        except docker.errors.NotFound:
            pass

    request.addfinalizer(_cleanup)

    container.reload()
    assert container.status == "running"
    port_mapping = container.attrs["NetworkSettings"]["Ports"]
    if all_ports:
        port = port_mapping["8888/tcp"][0]["HostPort"]

    url = "http://{}:{}".format(host, port)
    for i in range(5):
        try:
            r = requests.get(url)
            r.raise_for_status()
        except Exception as e:
            print("No response from {}: {}".format(url, e))
            container.reload()
            assert container.status == "running"
            time.sleep(3)
            continue
        else:
            break
    else:
        pytest.fail("Never succeeded in talking to %s" % url)
    assert "Directory listing" in r.text


def test_all_port_mapping_response(request, tmpdir):
    """
    Deploy container and test if all port exposed works as expected
    """
    read_port_mapping_response(request, tmpdir, all_ports=True)


@pytest.mark.parametrize(
    "host, protocol", [(None, None), ("127.0.0.1", None), (None, "/tcp")]
)
def test_port_mapping(request, tmpdir, host, protocol):
    """Test a port mapping"""
    port = str(random.randint(50000, 51000))
    read_port_mapping_response(request, tmpdir, host=host, port=port, protocol=protocol)


@pytest.mark.parametrize(
    "port_str, port_dict",
    [
        ("8000", {"8000/tcp": "8000"}),
        ("8000:9000", {"9000/tcp": "8000"}),
        ("127.0.0.1:8000:9000", {"9000/tcp": ("127.0.0.1", "8000")}),
    ],
)
def test_port_args(port_str, port_dict):
    app = make_r2d(["-p", port_str, "."])
    assert app.ports == port_dict
