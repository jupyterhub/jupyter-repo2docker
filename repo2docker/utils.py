from contextlib import contextmanager
from functools import partial
import os
import re
import subprocess
import chardet
import tempfile
import tarfile

from shutil import copystat, copy2

from traitlets import Integer, TraitError


def execute_cmd(cmd, capture=False, **kwargs):
    """
    Call given command, yielding output line by line if capture=True.

    Must be yielded from.
    """
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT

    proc = subprocess.Popen(cmd, **kwargs)

    if not capture:
        # not capturing output, let subprocesses talk directly to terminal
        ret = proc.wait()
        if ret != 0:
            raise subprocess.CalledProcessError(ret, cmd)
        return

    # Capture output for logging.
    # Each line will be yielded as text.
    # This should behave the same as .readline(), but splits on `\r` OR `\n`,
    # not just `\n`.
    buf = []

    def flush():
        """Flush next line of the buffer"""
        line = b"".join(buf).decode("utf8", "replace")
        buf[:] = []
        return line

    c_last = ""
    try:
        for c in iter(partial(proc.stdout.read, 1), b""):
            if c_last == b"\r" and buf and c != b"\n":
                yield flush()
            buf.append(c)
            if c == b"\n":
                yield flush()
            c_last = c
        if buf:
            yield flush()
    finally:
        ret = proc.wait()
        if ret != 0:
            raise subprocess.CalledProcessError(ret, cmd)


@contextmanager
def chdir(path):
    """Change working directory to `path` and restore it again

    This context maanger is useful if `path` stops existing during your
    operations.
    """
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)


@contextmanager
def open_guess_encoding(path):
    """
    Open a file in text mode, specifying its encoding,
    that we guess using chardet.
    """
    detector = chardet.universaldetector.UniversalDetector()
    with open(path, "rb") as f:
        for line in f.readlines():
            detector.feed(line)
            if detector.done:
                break
    detector.close()

    file = open(path, encoding=detector.result["encoding"])
    try:
        yield file
    finally:
        file.close()


def validate_and_generate_port_mapping(port_mappings):
    """
    Validate a list of port mappings and return a dictionary of port mappings.

    Args:
        port_mappings (list): List of strings of format
            `'host_port:container_port'` with optional tcp udp values and host
            network interface

    Returns:
        Dictionary of port mappings in the format accepted by docker-py's
        `containers.run()` method (https://docker-py.readthedocs.io/en/stable/containers.html)

    Raises:
        Exception on invalid port mapping

    Note:
        One limitation of repo2docker is it cannot bind a
        single container_port to multiple host_ports
        (docker-py supports this but repo2docker does not)
    """

    def check_port(port):
        try:
            p = int(port)
        except ValueError as e:
            raise ValueError(
                'Port specification "{}" has ' "an invalid port.".format(mapping)
            )
        if p > 65535:
            raise ValueError(
                'Port specification "{}" specifies '
                "a port above 65535.".format(mapping)
            )
        return port

    def check_port_string(p):
        parts = p.split("/")
        if len(parts) == 2:  # 134/tcp
            port, protocol = parts
            if protocol not in ("tcp", "udp"):
                raise ValueError(
                    'Port specification "{}" has '
                    "an invalid protocol.".format(mapping)
                )
        elif len(parts) == 1:
            port = parts[0]
            protocol = "tcp"

        check_port(port)

        return "/".join((port, protocol))

    ports = {}
    if port_mappings is None:
        return ports

    for mapping in port_mappings:
        parts = mapping.split(":")

        *host, container_port = parts
        # just a port
        if len(host) == 1:
            host = check_port(host[0])
        else:
            host = tuple((host[0], check_port(host[1])))

        container_port = check_port_string(container_port)
        ports[container_port] = host

    return ports


def is_valid_docker_image_name(image_name):
    """
    Determine if image name is valid for docker using strict pattern.

    Function that constructs a regex representing the docker image name and
    tests it against the given image_name. Reference Regex definition in
    https://github.com/docker/distribution/blob/master/reference/regexp.go
    The definition uses a stricter pattern than the docker default.

    Args:
        image_name: string representing a docker image name

    Returns:
        True if image_name is valid, else False

    Example:
        'test.Com/name:latest' is a valid tag

        'Test/name:latest' is not a valid tag

    Note:
        This function has a stricter pattern than
        https://github.com/docker/distribution/blob/master/reference/regexp.go

        This pattern will not allow cases like `TEST.com/name:latest` though
        docker considers it a valid tag.
    """
    reference_regex = re.compile(
        r"""
        ^  # Anchored at start and end of string

        (  # Start capturing name

        (?:  # start grouping the optional registry domain name part

        (?:[a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])  # lowercase only '<domain-name-component>'

        (?:  # start optional group

        # multiple repetitions of pattern '.<domain-name-component>'
        (?:\.(?:[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]))+

        )?  # end optional grouping part of the '.' separated domain name

        (?::[0-9]+)?/  # '<domain-name>' followed by an optional '<port>' component followed by '/' literal

        )?  # end grouping the optional registry domain part

        # start <name-pattern>
        [a-z0-9]+   # must have a <name-component>
        (?:
        (?:(?:[\._]|__|[-]*)[a-z0-9]+)+  # repeat the pattern '<separator><name-component>'
        )?  # optionally have multiple repetitions of the above line
        # end <name-pattern>

        (?:  # start optional name components

        (?:  # start multiple repetitions

        /   # separate multiple name components by /
        # start <name-pattern>
        [a-z0-9]+                        # must have a <name-component>
        (?:
        (?:(?:[\._]|__|[-]*)[a-z0-9]+)+  # repeat the pattern '<separator><name-component>'
        )?                               # optionally have multiple repetitions of the above line
        # end <name-pattern>

        )+  # multiple repetitions of the pattern '/<name-component><separator><name-component>'

        )?  # optionally have the above group

        )   # end capturing name

        (?::([\w][\w.-]{0,127}))?    # optional capture <tag-pattern>=':<tag>'
        # optionally capture <digest-pattern>='@<digest>'
        (?:@[A-Za-z][A-Za-z0-9]*(?:[-_+.][A-Za-z][A-Za-z0-9]*)*[:][A-Fa-f0-9]{32,})?
        $
        """,
        re.VERBOSE,
    )

    return reference_regex.match(image_name) is not None


class ByteSpecification(Integer):
    """
    Allow easily specifying bytes in units of 1024 with suffixes

    Suffixes allowed are:
      - K -> Kilobyte
      - M -> Megabyte
      - G -> Gigabyte
      - T -> Terabyte

    Stolen from JupyterHub
    """

    UNIT_SUFFIXES = {
        "K": 1024,
        "M": 1024 * 1024,
        "G": 1024 * 1024 * 1024,
        "T": 1024 * 1024 * 1024 * 1024,
    }

    # Default to allowing None as a value
    allow_none = True

    def validate(self, obj, value):
        """
        Validate that the passed-in value is a valid memory specification

        If value is a pure int, it is taken as a byte value.
        If value has one of the unit suffixes, it is converted into the
        appropriate pure byte value.
        """
        if isinstance(value, (int, float)):
            return int(value)

        try:
            num = float(value[:-1])
        except ValueError:
            raise TraitError(
                "{val} is not a valid memory specification. "
                "Must be an int or a string with suffix K, M, G, T".format(val=value)
            )
        suffix = value[-1]
        if suffix not in self.UNIT_SUFFIXES:
            raise TraitError(
                "{val} is not a valid memory specification. "
                "Must be an int or a string with suffix K, M, G, T".format(val=value)
            )
        else:
            return int(float(num) * self.UNIT_SUFFIXES[suffix])


def check_ref(ref, cwd=None):
    """Prepare a ref and ensure it works with git reset --hard."""
    # Try original ref, then trying a remote ref, then removing remote
    refs = [
        ref,  # Original ref
        "/".join(["origin", ref]),  # In case its a remote branch
        ref.split("/")[-1],
    ]  # In case partial commit w/ remote

    hash = None
    for i_ref in refs:
        call = ["git", "rev-parse", "--quiet", i_ref]
        try:
            # If success, output will be <hash>
            response = subprocess.check_output(call, stderr=subprocess.DEVNULL, cwd=cwd)
            hash = response.decode().strip()
        except Exception:
            # We'll throw an error later if no refs resolve
            pass
    return hash


class Error(OSError):
    pass


# a copy of shutil.copytree() that is ok with the target directory
# already existing
def copytree(
    src,
    dst,
    symlinks=False,
    ignore=None,
    copy_function=copy2,
    ignore_dangling_symlinks=False,
):
    """Recursively copy a directory tree.
    The destination directory must not already exist.
    If exception(s) occur, an Error is raised with a list of reasons.
    If the optional symlinks flag is true, symbolic links in the
    source tree result in symbolic links in the destination tree; if
    it is false, the contents of the files pointed to by symbolic
    links are copied. If the file pointed by the symlink doesn't
    exist, an exception will be added in the list of errors raised in
    an Error exception at the end of the copy process.
    You can set the optional ignore_dangling_symlinks flag to true if you
    want to silence this exception. Notice that this has no effect on
    platforms that don't support os.symlink.
    The optional ignore argument is a callable. If given, it
    is called with the `src` parameter, which is the directory
    being visited by copytree(), and `names` which is the list of
    `src` contents, as returned by os.listdir():
        callable(src, names) -> ignored_names
    Since copytree() is called recursively, the callable will be
    called once for each directory that is copied. It returns a
    list of names relative to the `src` directory that should
    not be copied.
    The optional copy_function argument is a callable that will be used
    to copy each file. It will be called with the source path and the
    destination path as arguments. By default, copy2() is used, but any
    function that supports the same signature (like copy()) can be used.
    """
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    os.makedirs(dst, exist_ok=True)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if os.path.islink(srcname):
                linkto = os.readlink(srcname)
                if symlinks:
                    # We can't just leave it to `copy_function` because legacy
                    # code with a custom `copy_function` may rely on copytree
                    # doing the right thing.
                    os.symlink(linkto, dstname)
                    copystat(srcname, dstname, follow_symlinks=not symlinks)
                else:
                    # ignore dangling symlink if the flag is on
                    if not os.path.exists(linkto) and ignore_dangling_symlinks:
                        continue
                    # otherwise let the copy occurs. copy2 will raise an error
                    if os.path.isdir(srcname):
                        copytree(srcname, dstname, symlinks, ignore, copy_function)
                    else:
                        copy_function(srcname, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks, ignore, copy_function)
            else:
                # Will raise a SpecialFileError for unsupported file types
                copy_function(srcname, dstname)
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except Error as err:
            errors.extend(err.args[0])
        except OSError as why:
            errors.append((srcname, dstname, str(why)))
    try:
        copystat(src, dst)
    except OSError as why:
        # Copying file access times may fail on Windows
        if getattr(why, "winerror", None) is None:
            errors.append((src, dst, str(why)))
    if errors:
        raise Error(errors)
    return dst


def deep_get(dikt, path):
    """Get a value located in `path` from a nested dictionary.

    Use a string separated by periods as the path to access
    values in a nested dictionary:

    deep_get(data, "data.files.0") == data["data"]["files"][0]
    """
    value = dikt
    for component in path.split("."):
        if component.isdigit():
            value = value[int(component)]
        else:
            value = value[component]
    return value


# doi_regexp, is_doi, and normalize_doi are from idutils (https://github.com/inveniosoftware/idutils)
# Copyright (C) 2015-2018 CERN.
# Copyright (C) 2018 Alan Rubin.
# Licensed under BSD-3-Clause license
doi_regexp = re.compile(
    r"(doi:\s*|(?:https?://)?(?:dx\.)?doi\.org/)?(10\.\d+(.\d+)*/.+)$", flags=re.I
)


def is_doi(val):
    """Returns None if val doesn't match pattern of a DOI.
    http://en.wikipedia.org/wiki/Digital_object_identifier."""
    return doi_regexp.match(val)


def normalize_doi(val):
    """Return just the DOI (e.g. 10.1234/jshd123)
    from a val that could include a url or doi
    (e.g. https://doi.org/10.1234/jshd123)"""
    m = doi_regexp.match(val)
    return m.group(2)


def is_local_pip_requirement(line):
    """Return whether a pip requirement (e.g. in requirements.txt file) references a local file"""
    # trim comments and skip empty lines
    line = line.split("#", 1)[0].strip()
    if not line:
        return False

    if line.startswith(("-r", "-c")):
        # local -r or -c references break isolation
        return True

    if line.startswith(("--requirement", "--constraint")):
        # as above but flags are spelt out
        return True

    # the `--pre` flag is a global flag and should appear on a line by itself
    # we just care that this isn't a "local pip requirement"
    if line.startswith("--pre"):
        return False

    # strip off things like `--editable=`. Long form arguments require a =
    # if there is no = it is probably because the line contains
    # a syntax error or our "parser" is too simplistic
    if line.startswith("--") and "=" in line:
        _, line = line.split("=", 1)

    # strip off short form arguments like `-e`. Short form arguments can be
    # followed by a space `-e foo` or use `-e=foo`. The latter is not handled
    # here. We can deal with it when we see someone using it.
    if line.startswith("-"):
        _, *rest = line.split(None, 1)
        if not rest:
            # no argument after `--flag`, skip line
            return False
        line = rest[0]

    if "file://" in line:
        # file references break isolation
        return True

    if "://" in line:
        # handle git://../local/file
        path = line.split("://", 1)[1]
    else:
        path = line

    if path.startswith("."):
        # references a local file
        return True

    return False


# copied from:
# https://github.com/docker/docker-py/blob/master/tests/helpers.py#L29-L38
def archive_repo(path):
    f = tempfile.NamedTemporaryFile()
    t = tarfile.open(mode="w", fileobj=f)

    abs_path = os.path.abspath(path)
    t.add(abs_path, arcname=os.path.basename(path), recursive=True)

    t.close()
    f.seek(0)
    return f
