Test that node 10 and npm 6 are installed and runnable.

To create image.tar created manually:

- Run `repo2docker tests/base/node10`
- Copy image name from the line `Successfully tagged  ...` in the log
- `docker save --output image.tar <image name>`
