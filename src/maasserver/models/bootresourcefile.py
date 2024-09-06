# Copyright 2014-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Boot Resource File."""

from __future__ import annotations

from django.db.models import (
    BigIntegerField,
    CASCADE,
    CharField,
    Exists,
    ForeignKey,
    Index,
    JSONField,
    Manager,
    OuterRef,
    QuerySet,
    Sum,
)

from maasserver.enum import (
    BOOT_RESOURCE_FILE_TYPE,
    BOOT_RESOURCE_FILE_TYPE_CHOICES,
)
from maasserver.models.bootresource import BootResource
from maasserver.models.bootresourceset import BootResourceSet
from maasserver.models.cleansave import CleanSave
from maasserver.models.largefile import LargeFile
from maasserver.models.node import RegionController
from maasserver.models.timestampedmodel import TimestampedModel
from maasserver.utils.bootresource import LocalBootResourceFile
from maasserver.workflow import execute_workflow
from maasserver.workflow.bootresource import (
    ResourceDeleteParam,
    ResourceIdentifier,
)

SHORTSHA256_MIN_PREFIX_LEN = 7


class BootResourceFileManager(Manager):
    def filestore_remove_file(self, rfile: BootResourceFile):
        qs = self.filter(sha256=rfile.sha256).exclude(id=rfile.id)
        if not qs.exists():
            execute_workflow(
                "delete-bootresource",
                f"bootresource-del:{rfile.id}",
                ResourceDeleteParam(
                    files=[
                        ResourceIdentifier(
                            sha256=str(rfile.sha256),
                            filename_on_disk=str(rfile.filename_on_disk),
                        )
                    ]
                ),
            )
        rfile.bootresourcefilesync_set.all().delete()

    def calculate_filename_on_disk(self, sha256: str):
        # If a file with the same sha already exists, then we have to use the same filename_on_disk id.
        matching_resource = BootResourceFile.objects.filter(
            sha256=sha256
        ).first()
        if matching_resource:
            return matching_resource.filename_on_disk

        collisions = list(
            BootResourceFile.objects.filter(
                filename_on_disk__startswith=sha256[
                    :SHORTSHA256_MIN_PREFIX_LEN
                ]
            ).values_list("filename_on_disk", flat=True)
        )
        if len(collisions) > 0:
            # Keep adding chars until we don't have a collision. We are going to find a suitable prefix here since we
            # have already excluded that there is an image with the same full sha.
            for i in range(SHORTSHA256_MIN_PREFIX_LEN + 1, 64):
                if all(not f.startswith(sha256[:i]) for f in collisions):
                    return sha256[:i]
        else:
            return sha256[:SHORTSHA256_MIN_PREFIX_LEN]

    def filestore_remove_files(self, rfile_qs: QuerySet):
        other_res = self.filter(sha256=OuterRef("sha256")).exclude(
            id=OuterRef("id")
        )
        rfiles = rfile_qs.annotate(shared=Exists(other_res)).values(
            "sha256", "filename_on_disk", "shared"
        )
        to_remove = [
            ResourceIdentifier(
                sha256=file["sha256"],
                filename_on_disk=file["filename_on_disk"],
            )
            for file in rfiles
            if not file["shared"]
        ]
        if to_remove:
            execute_workflow(
                "delete-bootresource",
                param=ResourceDeleteParam(files=to_remove),
            )
        BootResourceFileSync.objects.filter(file__in=rfile_qs).delete()

    def filestore_remove_set(self, rset: BootResourceSet):
        qs = self.filter(resource_set=rset)
        self.filestore_remove_files(qs)

    def filestore_remove_sets(self, qsset: QuerySet):
        qs = self.filter(resource_set__in=qsset)
        self.filestore_remove_files(qs)

    def filestore_remove_resource(self, resource: BootResource):
        qs = self.filter(resource_set__resource=resource)
        self.filestore_remove_files(qs)

    def filestore_remove_resources(self, resources: QuerySet):
        qs = self.filter(resource_set__resource__in=resources)
        self.filestore_remove_files(qs)


class BootResourceFile(CleanSave, TimestampedModel):
    """File associated with a `BootResourceSet`.

    Each `BootResourceSet` contains a set of files. For user uploaded boot
    resources this is only one file. For synced and generated resources this
    can be multiple files.

    :ivar resource_set: `BootResourceSet` file belongs to. When
        `BootResourceSet` is deleted, this `BootResourceFile` will be deleted.
    :ivar filename: Name of the file.
    :ivar filetype: Type of the file. See the vocabulary
        :class:`BOOT_RESOURCE_FILE_TYPE`.
    :ivar extra: Extra information about the file. This is only used
        for synced Ubuntu images.
    """

    class Meta:
        unique_together = (("resource_set", "filename"),)
        indexes = [
            Index(fields=["sha256"]),
        ]

    objects = BootResourceFileManager()

    resource_set = ForeignKey(
        BootResourceSet,
        related_name="files",
        editable=False,
        on_delete=CASCADE,
    )

    largefile = ForeignKey(LargeFile, on_delete=CASCADE, null=True)

    filename = CharField(max_length=255, editable=False)

    filetype = CharField(
        max_length=20,
        choices=BOOT_RESOURCE_FILE_TYPE_CHOICES,
        default=BOOT_RESOURCE_FILE_TYPE.ROOT_TGZ,
        editable=False,
    )

    extra = JSONField(blank=True, default=dict)

    sha256 = CharField(max_length=64, blank=True)

    filename_on_disk = CharField(max_length=64, blank=True)

    size = BigIntegerField(default=0)

    @property
    def sync_progress(self) -> float:
        """Percentage complete for all files in the set."""
        from maasserver.models.node import RegionController

        if not self.bootresourcefilesync_set.exists():
            return 0.0
        sync_size = (
            self.bootresourcefilesync_set.all().aggregate(
                total_size=Sum("size")
            )["total_size"]
            or 0
        )
        n_regions = RegionController.objects.count()
        return 100.0 * sync_size / (self.size * n_regions)

    @property
    def complete(self) -> bool:
        """True if all regions are synchronized."""
        return self.sync_progress == 100.0

    @property
    def has_complete_copy(self) -> bool:
        """True if at least one Region has a complete copy of this file"""
        return self.bootresourcefilesync_set.filter(size=self.size).exists()

    def get_regions_with_complete_copy(self) -> list[str]:
        """Get synchronisation sources

        List Region Controllers that have the complete file.

        Returns:
            list[str]: A list of system IDs
        """
        return [
            *self.bootresourcefilesync_set.filter(size=self.size).values_list(
                "region__system_id", flat=True
            )
        ]

    def local_file(self) -> LocalBootResourceFile:
        return LocalBootResourceFile(
            self.sha256, self.filename_on_disk, self.size
        )

    def __str__(self):
        return f"<BootResourceFile {self.filename}/{self.filetype}>"


class BootResourceFileSync(CleanSave, TimestampedModel):
    class Meta:
        unique_together = (("file", "region"),)

    file = ForeignKey(BootResourceFile, on_delete=CASCADE)

    region = ForeignKey(RegionController, on_delete=CASCADE)

    size = BigIntegerField(default=0)

    def __str__(self):
        return f"<BootResourceFileSync {self.file.filename}@{self.region.system_id} = {self.size}B>"
