# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from maascommon.enums.power_driver import PowerTypeEnum
from maasservicelayer.models.base import MaasTimestampedBaseModel


class Bmc(MaasTimestampedBaseModel):
    # TODO: model to be completed.
    power_type: PowerTypeEnum
    power_parameters: dict
