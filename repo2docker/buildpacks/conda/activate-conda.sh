#!/bin/bash -x
# enable conda and activate the notebook environment
CONDA_PROFILE="${CONDA_DIR}/etc/profile.d/conda.sh"
test -f $CONDA_PROFILE && . $CONDA_PROFILE
if [[ "${KERNEL_PYTHON_PREFIX}" != "${NB_PYTHON_PREFIX}" ]]; then
    # if the kernel is a separate env, stack them
    # so both are on PATH, notebook first
    conda activate ${KERNEL_PYTHON_PREFIX}
    conda activate --stack ${NB_PYTHON_PREFIX}

    # even though it's second on $PATH
    # make sure CONDA_DEFAULT_ENV is the *kernel* env
    # so that `!conda install PKG` installs in the kernel env
    # where user packages are installed, not the notebook env
    # which only contains UI when the two are different
    export CONDA_DEFAULT_ENV="${KERNEL_PYTHON_PREFIX}"
else
    CONDA_DEFAULT_ENV=${NB_PYTHON_PREFIX}
fi

echo "Activating default conda environment ${CONDA_DEFAULT_ENV}"
conda activate ${CONDA_DEFAULT_ENV}
