from enum import Enum


class SshKeysProtocolType(str, Enum):
    # Launchpad
    LP = "lp"

    # Github
    GH = "gh"

    def __str__(self):
        return str(self.value)
