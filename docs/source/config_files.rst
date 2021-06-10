.. _config-files:

===================
Configuration Files
===================

``repo2docker`` looks for configuration files in the repository being built
to determine how to build it. In general, ``repo2docker`` uses the same
configuration files as other software installation tools,
rather than creating new custom configuration files.

A number of ``repo2docker`` configuration files can be combined to compose more
complex setups.

The `binder examples <https://github.com/binder-examples>`_ organization on
GitHub contains a list of sample repositories for common configurations
that ``repo2docker`` can build with various configuration files such as
Python and R installation in a repository.

A list of supported configuration files (roughly in the order of build priority)
can be found on this page (and to the right).

.. _environment.yml:

``environment.yml`` - Install a conda environment
=================================================

``environment.yml`` is the standard configuration file used by `conda <https://conda.io>`_
that lets you install any kind of package,
including Python, R, and C/C++ packages.
``repo2docker`` does not use your ``environment.yml`` to create and activate a new conda environment.
Rather, it updates a base conda environment `defined here <https://github.com/jupyterhub/repo2docker/blob/master/repo2docker/buildpacks/conda/environment.yml>`_ with the packages listed in your ``environment.yml``.
This means that the environment will always have the same default name, not the name
specified in your ``environment.yml``.

.. note::

   You can install files from pip in your ``environment.yml`` as well.
   For example, see the `binder-examples environment.yml
   <https://github.com/binder-examples/python-conda_pip/blob/master/environment.yml>`_
   file.

You can also specify which Python version to install in your built environment
with ``environment.yml``. By default, ``repo2docker`` installs
|default_python| with your ``environment.yml`` unless you include the version of
Python in this file.  ``conda`` supports all versions of Python,
though ``repo2docker`` support is best with Python 3.7, 3.6, 3.5 and 2.7.

.. warning::
   If you include a Python version in a ``runtime.txt`` file in addition to your
   ``environment.yml``, your ``runtime.txt`` will be ignored.

.. _Pipfile:

``Pipfile`` and/or ``Pipfile.lock`` - Install a Python environment
==================================================================

`pipenv <https://github.com/pypa/pipenv/>`_ allows you to manage a virtual
environment Python dependencies. When using ``pipenv``, you end up with
``Pipfile`` and ``Pipfile.lock`` files. The lock file contains explicit details
about the packages that has been installed that met the criteria within the
``Pipfile``.

If both ``Pipfile`` and ``Pipfile.lock`` are found by repo2docker, the former
will be ignored in favor of the lock file. Also note that these files
distinguish packages and development packages and that repo2docker will install
both kinds.

.. _requirements.txt:

``requirements.txt`` - Install a Python environment
===================================================

This specifies a list of Python packages that should be installed in your
environment. Our
`requirements.txt example <https://github.com/binder-examples/requirements/blob/master/requirements.txt>`_
on GitHub shows a typical requirements file.


.. _setup.py:

``setup.py`` - Install Python packages
======================================

To install your repository like a Python package, you may include a
``setup.py`` file. repo2docker installs ``setup.py`` files by running
``pip install -e .``.

.. _Project.toml:

``Project.toml`` - Install a Julia environment
==============================================

A ``Project.toml`` (or ``JuliaProject.toml``) file can specify both the
version of Julia to be used and a list of Julia packages to be installed.
If a ``Manifest.toml`` is present, it will determine the exact versions
of the Julia packages that are installed.


.. _REQUIRE:

``REQUIRE`` - Install a Julia environment (legacy)
==================================================

A ``REQUIRE`` file can specify both the version of Julia to be used and
which Julia packages should be used. The use of ``REQUIRE`` is only
recommended for pre 1.0 Julia versions. The recommended way of installing
a Julia environment that uses Julia 1.0 or newer is to use a ``Project.toml``
file. If both a ``REQUIRE`` and a ``Project.toml`` file are detected,
the ``REQUIRE`` file is ignored. To see an example of a Julia repository
with ``REQUIRE`` and ``environment.yml``, visit
`binder-examples/julia-python <https://github.com/binder-examples/julia-python>`_.


.. _install.R:

``install.R`` - Install an R/RStudio environment
================================================

This is used to install R libraries pinned to a specific snapshot on
`MRAN <https://mran.microsoft.com/documents/rro/reproducibility>`_.
To set the date of the snapshot add a runtime.txt_.
For an example ``install.R`` file, visit our `example install.R file <https://github.com/binder-examples/r/blob/master/install.R>`_.


.. _apt.txt:

``apt.txt`` - Install packages with apt-get
===========================================

A list of Debian packages that should be installed. The base image used is usually the latest released
version of Ubuntu.

We use ``apt.txt``, for example, to install LaTeX in our
`example apt.txt for LaTeX <https://github.com/binder-examples/latex/blob/master/apt.txt>`_.


.. _DESCRIPTION:

``DESCRIPTION`` - Install an R package
======================================

To install your repository like an R package, you may include a
``DESCRIPTION`` file. repo2docker installs the package and dependencies
from the ``DESCRIPTION`` by running ``devtools::install_git(".")``.

You also need to have a ``runtime.txt`` file that is formatted as
``r-<YYYY>-<MM>-<DD>``, where YYYY-MM-DD is a snapshot of MRAN that will be
used for your R installation.


.. _postBuild:

``postBuild`` - Run code after installing the environment
=========================================================

A script that can contain arbitrary commands to be run after the whole repository has been built. If you
want this to be a shell script, make sure the first line is ``#!/bin/bash``.

Note that by default the build will not be stopped if an error occurs inside a shell script.
You should include ``set -e`` or the equivalent at the start of the script to avoid errors being silently ignored.

An example use-case of ``postBuild`` file is JupyterLab's demo on mybinder.org.
It uses a ``postBuild`` file in a folder called ``binder`` to `prepare
their demo for binder <https://github.com/jupyterlab/jupyterlab-demo/blob/master/binder/postBuild>`_.


.. _start:

``start`` - Run code before the user sessions starts
====================================================

A script that can contain simple commands to be run at runtime (as an
`ENTRYPOINT <https://docs.docker.com/engine/reference/builder/#entrypoint>`_
to the docker container). If you want this to be a shell script, make sure the
first line is ``#!/bin/bash``. The last line must be ``exec "$@"``
or equivalent.

Use this to set environment variables that software installed in your container
expects to be set. This script is executed each time your binder is started and
should at most take a few seconds to run.

If you only need to run things once during the build phase use :ref:`postBuild`.


.. TODO: Discuss runtime limits, best practices, etc.

.. _runtime.txt:

``runtime.txt`` - Specifying runtimes
=====================================

Sometimes you want to specify the version of the runtime
(e.g. the version of Python or R),
but the environment specification format will not let you specify this information
(e.g. requirements.txt or install.R).
For these cases, we have a special file, ``runtime.txt``.

.. note::

   ``runtime.txt`` is only supported when used with environment specifications
   that do not already support specifying the runtime
   (when using ``environment.yml`` for conda or ``Project.toml`` for Julia,
   ``runtime.txt`` will be ignored).

Have ``python-x.y`` in ``runtime.txt`` to run the repository with Python version x.y.
See our `Python2 example repository <https://github.com/binder-examples/python2_runtime/blob/master/runtime.txt>`_.

Have ``r-<RVERSION>-<YYYY>-<MM>-<DD>`` in ``runtime.txt`` to run the repository with R version RVERSION and libraries from a YYYY-MM-DD snapshot of `MRAN <https://mran.microsoft.com/documents/rro/reproducibility>`_.
RVERSION can be set to 3.4, 3.5, 3.6, or to patch releases for the 3.5 and 3.6 series.
If you do not specify a version, the latest release will be used (currently R 3.6).
See our `R example repository <https://github.com/binder-examples/r/blob/master/runtime.txt>`_.

.. _default.nix:

``default.nix`` - the nix package manager
=========================================

Specify packages to be installed by the `nix package manager <https://github.com/NixOS/nixpkgs>`_.
When you use this config file all other configuration files (like ``requirements.txt``)
that specify packages are ignored. When using ``nix`` you have to specify all
packages and dependencies explicitly, including the Jupyter notebook package that
repo2docker expects to be installed. If you do not install Jupyter explicitly
repo2docker will no be able to start your container.

`nix-shell <https://nixos.org/nix/manual/#sec-nix-shell>`_ is used to evaluate
a ``nix`` expression written in a ``default.nix`` file. Make sure to
`pin your nixpkgs <https://discourse.nixos.org/t/nixops-pinning-nixpkgs/734>`_
to produce a reproducible environment.

To see an example repository visit
`nix binder example <https://github.com/binder-examples/nix>`_.

.. _manifest.scm:

``manifest.scm`` - the Guix package manager
===========================================

Specify packages to be installed by the `Guix package manager <https://guix.gnu.org/>`_.
All packages specified in |manifest|_ will be installed in a container using |guix_package|_. In addition, you can use different `channels <https://guix.gnu.org/manual/en/html_node/Channels.html>`_ rather
than the ones available by default (official channels of GNU Guix 1.3.0).
You must describe such channels in a ``channels.scm`` file which will be used
alongside ``manifest.scm`` with the |guix_time-machine|_ command. Furthermore, using a ``channels.scm`` file lets you `pin a specific revision <https://guix.gnu.org/manual/en/html_node/Replicating-Guix.html>`_ of Guix, allowing you to unambiguously specific the software environment to reproduce.

For more information about Guix please read the `manual <https://guix.gnu.org/manual/en/guix.html>`_.

.. |manifest| replace:: ``manifest.scm``
.. _manifest: https://guix.gnu.org/manual/en/html_node/Invoking-guix-package.html#index-profile-manifesthy

.. |guix_package| replace:: ``guix package``
.. _guix_package: https://guix.gnu.org/manual/en/html_node/Invoking-guix-package.html#Invoking-guix-package

.. |guix_time-machine| replace:: ``guix time-machine``
.. _guix_time-machine: https://guix.gnu.org/manual/en/html_node/Invoking-guix-time_002dmachine.html

``Dockerfile`` - Advanced environments
======================================

In the majority of cases, providing your own Dockerfile is not necessary as the base
images provide core functionality, compact image sizes, and efficient builds. We recommend
trying the other configuration files before deciding to use your own Dockerfile.

With Dockerfiles, a regular Docker build will be performed.

.. note::
    If a Dockerfile is present, all other configuration files will be ignored.

See the `Advanced Binder Documentation <https://mybinder.readthedocs.io/en/latest/tutorials/dockerfile.html>`_ for
best-practices with Dockerfiles.
