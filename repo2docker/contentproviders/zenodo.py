import os
import json
import shutil

from os import makedirs
from os import path
from urllib.request import Request
from urllib.error import HTTPError

from .doi import DoiProvider
from ..utils import copytree, deep_get


class Zenodo(DoiProvider):
    """Provide contents of a Zenodo deposit."""

    def __init__(self):
        super().__init__()
        # We need the hostname (url where records are), api url (for metadata),
        # filepath (path to files in metadata), filename (path to filename in
        # metadata), download (path to file download URL), and type (path to item type in metadata)
        self.hosts = [
            {
                "hostname": ["https://zenodo.org/record/", "http://zenodo.org/record/"],
                "api": "https://zenodo.org/api/records/",
                "filepath": "files",
                "filename": "filename",
                "download": "links.download",
                "type": "metadata.upload_type",
            },
            {
                "hostname": [
                    "https://sandbox.zenodo.org/record/",
                    "http://sandbox.zenodo.org/record/",
                ],
                "api": "https://sandbox.zenodo.org/api/records/",
                "filepath": "files",
                "filename": "filename",
                "download": "links.download",
                "type": "metadata.upload_type",
            },
            {
                "hostname": [
                    "https://data.caltech.edu/records/",
                    "http://data.caltech.edu/records/",
                ],
                "api": "https://data.caltech.edu/api/record/",
                "filepath": "metadata.electronic_location_and_access",
                "filename": "electronic_name.0",
                "download": "uniform_resource_identifier",
                "type": "metadata.resourceType.resourceTypeGeneral",
            },
        ]

    def detect(self, doi, ref=None, extra_args=None):
        """Trigger this provider for things that resolve to a Zenodo/Invenio record"""
        url = self.doi2url(doi)

        for host in self.hosts:
            if any([url.startswith(s) for s in host["hostname"]]):
                self.record_id = url.rsplit("/", maxsplit=1)[1]
                return {"record": self.record_id, "host": host}

    def fetch(self, spec, output_dir, yield_output=False):
        """Fetch and unpack a Zenodo record"""
        record_id = spec["record"]
        host = spec["host"]

        yield "Fetching Zenodo record {}.\n".format(record_id)
        resp = self.urlopen(
            "{}{}".format(host["api"], record_id),
            headers={"accept": "application/json"},
        )

        record = resp.json()

        is_software = deep_get(record, host["type"]).lower() == "software"
        files = deep_get(record, host["filepath"])
        only_one_file = len(files) == 1
        for file_ref in files:
            for line in self.fetch_file(
                file_ref, host, output_dir, is_software and only_one_file
            ):
                yield line

    @property
    def content_id(self):
        """The Zenodo record ID as the content of a record is immutable"""
        return self.record_id
