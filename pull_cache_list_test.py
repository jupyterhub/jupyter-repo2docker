import docker
import json

# TODO: print statements to be replaced with logger

# Set up docker client
client = docker.APIClient(base_url="unix://var/run/docker.sock")

# List of example images we'd like to use as a cache
cache_from = [
    "sgibson91/binderhub-setup",
    "sgibson91/binderhub-setup:latest",
    "sgibson91/binderhub-setup:1.2.1",
]


def pull_cache_list(cache_from):
    """Run `docker pull` for the images in the cache_from list. These images
    will then be available locally for the build phase.

    Arguments:
        cache_from {list} -- List of the desired images to use as a cache
    """
    for image in cache_from:
        # Check if a specific image tag has been provided by looking for ':' in
        # the image name. If no tag has been provided, default to 'latest'.
        if ":" in image:
            image_name, tag = image.split(":")
        else:
            print("No tag present. Using 'latest'.")
            image_name = image
            tag = "latest"

        # Pull the image from Docker Hub and stream the progress to logs
        for line in client.pull(image_name, tag=tag, stream=True, decode=True):
            print(json.dumps(line, indent=2, sort_keys=True))


if __name__ == "__main__":
    pull_cache_list(cache_from)
