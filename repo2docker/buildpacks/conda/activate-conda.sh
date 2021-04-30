# enable conda and activate the notebook environment
export MAMBA_EXE="/tmp/bin/micromamba"
export MAMBA_ROOT_PREFIX="/srv/conda"
CONDA_PROFILE="${CONDA_DIR}/etc/profile.d/mamba.sh"
test -f $CONDA_PROFILE && . $CONDA_PROFILE
if [[ "${KERNEL_PYTHON_PREFIX}" != "${NB_PYTHON_PREFIX}" ]]; then
    # if the kernel is a separate env, stack them
    # so both are on PATH, notebook first
    micromamba activate ${KERNEL_PYTHON_PREFIX}
    micromamba activate  --stack ${NB_PYTHON_PREFIX}

    # even though it's second on $PATH
    # make sure CONDA_DEFAULT_ENV is the *kernel* env
    # so that `!conda install PKG` installs in the kernel env
    # where user packages are installed, not the notebook env
    # which only contains UI when the two are different
    export CONDA_DEFAULT_ENV="${KERNEL_PYTHON_PREFIX}"
else
    micromamba activate ${NB_PYTHON_PREFIX}
fi
