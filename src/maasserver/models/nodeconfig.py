from django.db.models import CASCADE, ForeignKey, TextField

from maascommon.enums.base import enum_choices
from maasserver.models.cleansave import CleanSave
from maasserver.models.timestampedmodel import TimestampedModel


class NODE_CONFIG_TYPE:
    """Type of node configuration."""

    DISCOVERED = "discovered"
    DEPLOYMENT = "deployment"


NODE_CONFIG_TYPE_CHOICES = enum_choices(NODE_CONFIG_TYPE)

# XXX we should eventually get rid of this as all call sites filtering by type
# should look for a specific type
NODE_CONFIG_DEFAULT = NODE_CONFIG_TYPE.DISCOVERED


class NodeConfig(CleanSave, TimestampedModel):
    class Meta:
        unique_together = ["node", "name"]

    name = TextField(
        choices=NODE_CONFIG_TYPE_CHOICES,
        default=NODE_CONFIG_DEFAULT,
    )
    node = ForeignKey("Node", on_delete=CASCADE)

    @property
    def special_filesystems(self):
        """Return special filesystems (e.g. tmpfs) for the config."""
        return self.filesystem_set.filter(
            block_device=None,
            partition=None,
        )


def create_default_nodeconfig(node):
    """Create the `discovered` NodeConfig for a Node."""
    node_config = NodeConfig.objects.create(node=node)
    node.current_config = node_config
    node.save()
