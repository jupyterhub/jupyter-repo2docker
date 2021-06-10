# This downloads and installs a pinned version of Guix using a pinned version of the installation script.
# Here is the commit associated with Guix version 1.3.0 the latest version when this script was written.
set -euxo pipefail

GUIX_COMMIT="a0178d34f582b50e9bdbb0403943129ae5b560ff"
BIN_VER="1.3.0x86_64-linux"
GUIX_SHA256="bcdeaa757cd42d2c9de4791272737e9ee0d518398403955f113611f4a893380a"

wget "https://git.savannah.gnu.org/cgit/guix.git/plain/etc/guix-install.sh?id=$GUIX_COMMIT"

echo "$GUIX_SHA256  guix-install.sh?id=$GUIX_COMMIT" | sha256sum -c

(yes || true) | BIN_VER=$BIN_VER bash guix-install.sh?id=$GUIX_COMMIT
