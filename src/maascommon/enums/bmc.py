#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).


class BMC_TYPE:
    """Valid BMC types."""

    DEFAULT = 0
    BMC = 0
    POD = 1


BMC_TYPE_CHOICES = ((BMC_TYPE.BMC, "BMC"), (BMC_TYPE.POD, "POD"))
