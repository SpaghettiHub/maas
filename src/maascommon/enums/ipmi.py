#  Copyright 2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import enum


class IPMICipherSuiteID(enum.StrEnum):
    SUITE_17 = "17"
    SUITE_3 = "3"
    DEFAULT = ""
    SUITE_8 = "8"
    SUITE_12 = "12"

    def __str__(self):
        return str(self.value)


@enum.unique
class IPMIPriviledgeLevel(enum.StrEnum):
    USER = "USER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"

    def __str__(self):
        return str(self.value)
