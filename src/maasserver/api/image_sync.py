# Copyright 2023 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from django.db.models import F
from django.shortcuts import get_object_or_404

from maasserver.api.support import admin_method, OperationsHandler
from maasserver.api.utils import get_optional_param
from maasserver.models.bootresourcefile import BootResourceFile
from maasserver.models.node import RegionController


class ImagesSyncProgressHandler(OperationsHandler):
    api_doc_section_name = "ImagesSyncProgress"
    update = delete = None
    fields = ()
    hidden = True

    @classmethod
    def resource_uri(cls, *args, **kwargs):
        return ("images_sync_progress_handler", [])

    @admin_method
    def read(self, request):
        with_sources = get_optional_param(request.GET, "sources", True)
        qs = (
            BootResourceFile.objects.prefetch_related(
                "bootresourcefilesync_set__region"
            )
            .filter(size=F("bootresourcefilesync__size"))
            .order_by("id")
        )
        return {
            file.id: {
                "sha256": file.sha256,
                "filename_on_disk": file.filename_on_disk,
                "size": file.size,
                "sources": (
                    file.bootresourcefilesync_set.all().values_list(
                        "region__system_id", flat=True
                    )
                    if with_sources
                    else []
                ),
            }
            for file in qs
        }

    @admin_method
    def create(self, request):
        data = request.data
        region = get_object_or_404(
            RegionController, system_id=data.get("system_id")
        )
        size = data.get("size")
        ids = data.getlist("ids")
        qs = BootResourceFile.objects.filter(id__in=ids).prefetch_related(
            "bootresourcefilesync_set"
        )
        for file in qs:
            file.bootresourcefilesync_set.update_or_create(
                defaults=dict(size=size),
                region=region,
            )


class ImageSyncProgressHandler(OperationsHandler):
    """Internal endpoint to update progress of image sync"""

    api_doc_section_name = "ImageSyncProgress"
    create = delete = None
    fields = ()
    hidden = True

    @classmethod
    def resource_uri(cls, file_id=None, system_id=None):
        f_id = "file_id"
        sys_id = "system_id"
        if file_id is not None:
            f_id = str(file_id)
        if system_id is not None:
            sys_id = system_id
        return (
            "image_sync_progress_handler",
            (
                f_id,
                sys_id,
            ),
        )

    @admin_method
    def update(self, request, file_id, system_id):
        data = request.data
        size = data.get("size", 0)
        boot_file = get_object_or_404(BootResourceFile, id=file_id)
        region = get_object_or_404(RegionController, system_id=system_id)
        boot_file.bootresourcefilesync_set.update_or_create(
            defaults=dict(size=size),
            region=region,
        )

    @admin_method
    def read(self, request, file_id, system_id):
        boot_file = get_object_or_404(BootResourceFile, id=file_id)
        region = get_object_or_404(RegionController, system_id=system_id)
        if boot_file.bootresourcefilesync_set.exists():
            syncstatus = boot_file.bootresourcefilesync_set.get(region=region)
        else:
            return {"size": 0}
        return {"size": syncstatus.size}
