.. _export-environment:

=============================================================================
How to automatically create a ``environment.yml`` that works with repo2docker
=============================================================================

This how-to explains how to create a ``environment.yml`` that specifies all
installed packages and their precise versions from your environment.


The challenge
=============

``conda env export -f environment.yml`` creates a strict export of all packages.
This is the most robust for reproducibility, but it does bake in potential
platform-specific packages, so you can only use an exported environment on the
same platform.

``repo2docker`` uses a linux based image as the starting point for every docker
image it creates. However a lot of people use OSX or Windows as their day to
day operating system. This means that the ``environment.yml`` created by a strict
export will not work with error messages saying that certain packages can not
be resolved (``ResolvePackageNotFound``).


The solution
============

Export your explicit install commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To get a minimal ``environment.yml`` that only contains the packages you
explicitly installed run
``conda env export --from-history -f environment.yml``. We recommend that you
use this option to create your ``environment.yml``. The resulting
``environment.yml`` then contains a loose pinning of the versions used, e.g.
``pandas=0.25`` if you explicitly requested this ``pandas`` version on
installation. If you didn't list a version constraint during installation, it
will also not be listed in your ``environment.yml``.

While this approach doesn't lead to perfect reproducibilty, it will contain
just the same packages as if you would recreate the enviroment with the same
commands again today.

Strict version export
~~~~~~~~~~~~~~~~~~~~~

Follow this procedure to create a strict export of your environment that will
work with ``repo2docker`` and sites like `mybinder.org <https://mybinder.org/>`_.

We will launch a terminal inside a basic docker image, install the packages
you need and then perform a strict export of the environment.

#. install repo2docker on your computer by following :ref:`install`
#. in a terminal launch a basic repository
   ``repo2docker https://github.com/binder-examples/conda-freeze``
   inside repo2docker
#. open the URL printed at the end in a browser, the URL should look like
   ``http://127.0.0.1:61037/?token=30e61ec80bda6dd0d14805ea76bb59e7b0cd78b5d6b436f0``
#. open a terminal by clicking "New -> Terminal" next to the "Upload" button on the
   right hand side of the webpage
#. install the packages your project requires with ``conda install <yourpackages>``
#. use ``conda env export`` to print the environment
#. copy and paste the environment you just printed into a ``environment.yml`` in
   your projects repository
#. close your browser tabs and exit the repo2docker session by pressing Ctrl-C.

This will give you a strict export of your environment that precisely pins the
versions of packages in your environment based on a linux environment.
