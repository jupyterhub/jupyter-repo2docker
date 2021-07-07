#!/bin/bash
# This downloads and installs a pinned version of micromamba
# and sets up the base environment
set -ex


cd $(dirname $0)

URL="https://github.com/mamba-org/boa-forge/releases/download/micromamba-nightly-21.5.31.1722/micromamba-nightly-linux-64"

# make sure we don't do anything funky with user's $HOME
# since this is run as root
unset HOME
mkdir -p ${CONDA_DIR}

time wget ${URL} && mkdir bin && mv micromamba-nightly-linux-64 bin/micromamba
chmod +x bin/micromamba

export MAMBA_ROOT_PREFIX=${CONDA_DIR}
export MAMBA_EXE="/tmp/bin/micromamba"

eval "$(./bin/micromamba shell hook -p ${CONDA_DIR} -s posix)"
./bin/micromamba shell init -s bash -p ${CONDA_DIR}

micromamba activate

export PATH="${PWD}/bin:$PATH"

cat <<EOT >> ${CONDA_DIR}/.condarc
channels:
  - conda-forge
  - defaults
auto_update_conda: false
show_channel_urls: true
update_dependencies: false
channel_priority: strict
EOT

echo "installing notebook env:"
cat /tmp/environment.yml
time micromamba create -p ${NB_PYTHON_PREFIX} -f /tmp/environment.yml

# empty conda history file,
# which seems to result in some effective pinning of packages in the initial env,
# which we don't intend.
# this file must not be *removed*, however
echo '' > ${NB_PYTHON_PREFIX}/conda-meta/history

if [[ -f /tmp/kernel-environment.yml ]]; then
    # install kernel env and register kernelspec
    echo "installing kernel env:"
    cat /tmp/kernel-environment.yml

    time micromamba create -p ${KERNEL_PYTHON_PREFIX} -f /tmp/kernel-environment.yml
    ${KERNEL_PYTHON_PREFIX}/bin/ipython kernel install --prefix "${NB_PYTHON_PREFIX}"
    echo '' > ${KERNEL_PYTHON_PREFIX}/conda-meta/history
    micromamba list -p ${KERNEL_PYTHON_PREFIX}
fi

# Clean things out!
time micromamba clean --all -y

# Remove the pip cache created as part of installing micromamba
rm -rf /root/.cache

chown -R $NB_USER:$NB_USER ${CONDA_DIR}

micromamba list -p ${NB_PYTHON_PREFIX}
