"""BuildPack for guix environments"""
import os

from ..base import BuildPack, BaseImage


class GuixBuildPack(BaseImage):
    """A Guix Package Manager BuildPack"""

    def get_path(self):
        """Return paths to be added to PATH environment variable"""
        return super().get_path() + [
            "/var/guix/profiles/per-user/${NB_USER}/.guix-profile/bin"
        ]


    def get_build_scripts(self):
        """
        Install a pinned version of Guix package manager,
        precised in guix-install.bash.
        """
        return super().get_build_scripts() + [
            (
                "root",
                """
                bash /tmp/.local/bin/guix-install.bash
                """,
            ),

        ]

    def get_build_script_files(self):

        """Copying guix installation script on the image"""
        return {
            "guix/guix-install.bash":
                "/tmp/.local/bin/guix-install.bash",
        }

    def get_assemble_scripts(self):
        """
        Launch Guix daemon with --disable-chroot to avoid the need
        of root privileges for the user.
        Make sure we never use Debian's python by error by renaming it
        then, as an user install packages listed in manifest.scm,
        use guix time-machine if channels.scm file exists.
        Finally set guix environment variables.
        """
        assemble_script ="""
                 /var/guix/profiles/per-user/root/current-guix/bin/guix-daemon \
                 --build-users-group=guixbuild --disable-chroot & \
                 mv /usr/bin/python /usr/bin/python.debian && \
                 su - $NB_USER -c '{}' && \
                 echo 'GUIX_PROFILE="/var/guix/profiles/per-user/$NB_USER/.guix-profile" ; \
                 source "$GUIX_PROFILE/etc/profile"'>> /etc/profile.d/99-guix.sh
                 """

        if os.path.exists(self.binder_path("channels.scm")):
            assemble_script = assemble_script.format(
                "guix time-machine -C  " + self.binder_path("channels.scm") +
                " -- package -m "  + self.binder_path("manifest.scm")
            )
        else:
            assemble_script = assemble_script.format(
                "guix package -m " + self.binder_path("manifest.scm")
            )
        return super().get_assemble_scripts() + [
            ( "root",
              assemble_script,
             )
        ]

    def detect(self):
        """Check if current repo should be built with the guix BuildPack"""
        return os.path.exists(self.binder_path("manifest.scm"))
    
