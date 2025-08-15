# Copyright 2015-2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Model for subnets."""

from __future__ import annotations

from operator import attrgetter
from typing import Iterable, Optional

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import RegexValidator
from django.db import connection
from django.db.models import (
    BooleanField,
    CharField,
    ForeignKey,
    GenericIPAddressField,
    IntegerField,
    Manager,
    PROTECT,
    Q,
    TextField,
)
from django.db.models.query import QuerySet
from netaddr import AddrFormatError, IPAddress, IPNetwork

from maascommon.enums.dns import DnsUpdateAction
from maascommon.utils.network import IPRangeStatistics, MAASIPSet
from maascommon.workflows.dhcp import (
    CONFIGURE_DHCP_WORKFLOW_NAME,
    ConfigureDHCPParam,
)
from maasserver.enum import (
    IPADDRESS_TYPE,
    IPRANGE_TYPE,
    RDNS_MODE,
    RDNS_MODE_CHOICES,
)
from maasserver.exceptions import (
    MAASAPIException,
    StaticIPAddressExhaustion,
    StaticIPAddressOutOfRange,
    StaticIPAddressUnavailable,
)
from maasserver.fields import CIDRField
from maasserver.models.cleansave import CleanSave
from maasserver.models.dnspublication import DNSPublication
from maasserver.models.timestampedmodel import TimestampedModel
from maasserver.sqlalchemy import service_layer
from maasserver.utils.orm import MAASQueriesMixin, post_commit_do
from maasserver.workflow import start_workflow
from provisioningserver.logger import get_maas_logger
from provisioningserver.utils.network import (
    make_ipaddress,
    MaybeIPAddress,
    parse_integer,
)

maaslog = get_maas_logger("subnet")

# Note: since subnets can be referenced in the API by name, if this regex is
# updated, then the regex in urls_api.py also needs to be udpated.
SUBNET_NAME_VALIDATOR = RegexValidator(r"^[.: \w/-]+$")

# Typing for list of IP addresses to exclude.
IPAddressExcludeList = Optional[Iterable[MaybeIPAddress]]


def create_cidr(network, subnet_mask=None):
    """Given the specified network and subnet mask, create a CIDR string.

    Discards any extra bits present in the 'network'. (bits which overlap
    zeroes in the netmask)

    Returns the object in unicode format, so that this function can be used
    in database migrations (which do not support custom fields).

    :param network:The network
    :param subnet_mask:An IPv4 or IPv6 netmask or prefix length
    :return:An IPNetwork representing the CIDR.
    """
    if isinstance(network, IPNetwork) and subnet_mask is None:
        return str(network.cidr)
    else:
        network = make_ipaddress(network)
    if subnet_mask is None and isinstance(network, (bytes, str)):
        if "/" in network:
            return str(IPNetwork(network).cidr)
        else:
            assert False, "Network passed as CIDR string must contain '/'."  # noqa: B011
    network = str(make_ipaddress(network))
    if isinstance(subnet_mask, int):
        mask = str(subnet_mask)
    else:
        mask = str(make_ipaddress(subnet_mask))
    cidr = IPNetwork(network + "/" + mask).cidr
    return str(cidr)


class SubnetQueriesMixin(MAASQueriesMixin):
    find_subnets_with_ip_query = """
        SELECT DISTINCT subnet.*, masklen(subnet.cidr) "prefixlen"
        FROM
            maasserver_subnet AS subnet
        WHERE
            %s << subnet.cidr
        ORDER BY prefixlen DESC
        """

    def raw_subnets_containing_ip(self, ip):
        """Find the most specific Subnet the specified IP address belongs in."""
        return self.raw(self.find_subnets_with_ip_query, params=[str(ip)])

    # Note: << is the postgresql "is contained within" operator.
    # See http://www.postgresql.org/docs/8.4/static/functions-net.html
    find_best_subnet_for_ip_query = """
        SELECT
            subnet.*,
            vlan.dhcp_on "dhcp_on"
        FROM maasserver_subnet AS subnet
        INNER JOIN maasserver_vlan AS vlan
            ON subnet.vlan_id = vlan.id
        WHERE
            %s << subnet.cidr /* Specified IP is inside range */
        ORDER BY
            /* Pick subnet that is on a VLAN that is managed over a subnet
               that is not managed on a VLAN. */
            dhcp_on DESC
        LIMIT 1
        """

    def get_best_subnet_for_ip(self, ip: str) -> Subnet | None:
        """Find the most-specific managed Subnet the specified IP address
        belongs to."""
        ip = IPAddress(ip)
        if ip.is_ipv4_mapped():
            ip = ip.ipv4()
        subnets = self.raw(
            self.find_best_subnet_for_ip_query, params=[str(ip)]
        )

        for subnet in subnets:
            return subnet  # This is stable because the query is ordered.
        else:
            return None

    def validate_filter_specifiers(self, specifiers):
        """Validate the given filter string."""
        try:
            self.filter_by_specifiers(specifiers)
        except (ValueError, AddrFormatError) as e:
            raise ValidationError(e.message)  # noqa: B904

    def get_specifiers_q(self, specifiers, separator=":", **kwargs):
        """Returns a Q object for objects matching the given specifiers.

        Allows a number of types to be prefixed in front of each specifier:
            * 'ip:' Matches the subnet that best matches the given IP address.
            * 'cidr:' Matches a subnet with the exact given CIDR.
            * 'name': Matches a subnet with the given name.
            * 'vid:' Matches a subnet whose VLAN has the given VID.
                Can be used with a hexadecimal or binary string by prefixing
                it with '0x' or '0b'.
            ' 'vlan:' Synonym for 'vid' for compatibility with older MAAS
                versions.
            * 'space:' Matches the name of this subnet's VLAN's space.

        If no specifier is given, the input will be treated as a CIDR. If
        the input is not a valid CIDR, it will be treated as subnet name.

        :raise:AddrFormatError:If a specific IP address or CIDR is requested,
            but the address could not be parsed.

        :return:django.db.models.Q
        """
        # Circular imports.
        from maasserver.models import Fabric, Interface, VLAN

        # This dict is used by the constraints code to identify objects
        # with particular properties. Please note that changing the keys here
        # can impact backward compatibility, so use caution.
        specifier_types = {
            None: self._add_default_query,
            "cidr": self._add_unvalidated_cidr_query,
            "fabric": (Fabric.objects, "vlan__subnet"),
            "id": self._add_subnet_id_query,
            "interface": (Interface.objects, "ip_addresses__subnet"),
            "ip": self._add_ip_in_subnet_query,
            "name": "__name",
            "space": self._add_space_query,
            "vid": self._add_vlan_vid_query,
            "vlan": (VLAN.objects, "subnet"),
        }
        return super().get_specifiers_q(
            specifiers,
            specifier_types=specifier_types,
            separator=separator,
            **kwargs,
        )

    def _add_default_query(self, current_q, op, item):
        """If the item we're matching is an integer, first try to locate the
        subnet by its ID. Otherwise, try to parse it as a CIDR. If all else
        fails, search by the name.
        """
        id = self.get_object_id(item)
        if id is not None:
            return op(current_q, Q(id=id))

        try:
            ip = IPNetwork(item)
        except (AddrFormatError, ValueError):
            # The user didn't pass in a valid CIDR, so try the subnet name.
            return op(current_q, Q(name=item))
        else:
            cidr = str(ip.cidr)
            return op(current_q, Q(cidr=cidr))

    def _add_space_query(self, current_q, op, space):
        """Query for a related VLAN with the specified space."""
        # Circular imports.
        from maasserver.models import Space

        if space == Space.UNDEFINED:
            current_q = op(current_q, Q(vlan__space__isnull=True))
        else:
            space = Space.objects.get_object_by_specifiers_or_raise(space)
            current_q = op(current_q, Q(vlan__space=space))
        return current_q

    def _add_unvalidated_cidr_query(self, current_q, op, item):
        ip = IPNetwork(item)
        cidr = str(ip.cidr)
        current_q = op(current_q, Q(cidr=cidr))
        return current_q

    def _add_ip_in_subnet_query(self, current_q, op, item):
        # Try to validate this before it hits the database, since this
        # is going to be a raw query.
        item = str(IPAddress(item))
        # This is a special case. If a specific IP filter is included,
        # a custom query is needed to get the result. We can't chain
        # a raw query using Q without grabbing the IDs first.
        ids = self.get_id_list(self.raw_subnets_containing_ip(item))
        current_q = op(current_q, Q(id__in=ids))
        return current_q

    def _add_subnet_id_query(self, current_q, op, item):
        try:
            item = parse_integer(item)
        except ValueError:
            raise ValidationError("Subnet ID must be numeric.")  # noqa: B904
        else:
            current_q = op(current_q, Q(id=item))
            return current_q


class SubnetQuerySet(QuerySet, SubnetQueriesMixin):
    """Custom QuerySet which mixes in some additional queries specific to
    subnets. This needs to be a mixin because an identical method is needed on
    both the Manager and all QuerySets which result from calling the manager.
    """


class SubnetManager(Manager, SubnetQueriesMixin):
    """Manager for :class:`Subnet` model."""

    def get_queryset(self):
        queryset = SubnetQuerySet(self.model, using=self._db)
        return queryset

    def create_from_cidr(self, cidr, vlan=None):
        """Create a subnet from the given CIDR."""
        name = "subnet-" + str(cidr)
        from maasserver.models import VLAN

        if vlan is None:
            vlan = VLAN.objects.get_default_vlan()
        return self.create(name=name, cidr=cidr, vlan=vlan)

    def _find_fabric(self, fabric):
        from maasserver.models import Fabric

        if fabric is None:
            # If no Fabric is specified, use the default. (will always be 0)
            fabric = 0
        elif isinstance(fabric, Fabric):
            fabric = fabric.id
        else:
            fabric = int(fabric)
        return fabric

    def get_cidr_list_for_periodic_active_scan(self):
        """Returns the list of subnets which allow a periodic active scan.

        :return: list of `netaddr.IPNetwork` objects.
        """
        query = self.filter(active_discovery=True)
        return [
            IPNetwork(cidr) for cidr in query.values_list("cidr", flat=True)
        ]

    def get_subnet_or_404(self, specifiers, user, perm):
        """Fetch a `Subnet` by its id.  Raise exceptions if no `Subnet` with
        this id exists or if the provided user has not the required permission
        to access this `Subnet`.

        :param specifiers: A specifier to uniquely locate the Subnet.
        :type specifiers: unicode
        :param user: The user that should be used in the permission check.
        :type user: django.contrib.auth.models.User
        :param perm: The permission to assert that the user has on the node.
        :type perm: unicode
        :raises: django.http.Http404_,
            :class:`maasserver.exceptions.PermissionDenied`.

        .. _django.http.Http404: https://
           docs.djangoproject.com/en/dev/topics/http/views/
           #the-http404-exception
        """
        subnet = self.get_object_by_specifiers_or_raise(specifiers)
        if user.has_perm(perm, subnet):
            return subnet
        else:
            raise PermissionDenied()


class Subnet(CleanSave, TimestampedModel):
    def __init__(self, *args, **kwargs):
        assert "space" not in kwargs, "Subnets can no longer be in spaces."
        super().__init__(*args, **kwargs)
        self._previous_vlan_id = None
        self._previous_cidr = None
        self._previous_rdns_mode = None
        self._previous_allow_dns = None

    objects = SubnetManager()

    name = CharField(
        blank=False,
        editable=True,
        max_length=255,
        validators=[SUBNET_NAME_VALIDATOR],
        help_text="Identifying name for this subnet.",
    )

    description = TextField(null=False, blank=True)

    vlan = ForeignKey(
        "VLAN", editable=True, blank=False, null=False, on_delete=PROTECT
    )

    # XXX:fabric: unique constraint should be relaxed once proper support for
    # fabrics is implemented. The CIDR must be unique within a Fabric, not
    # globally unique.
    cidr = CIDRField(blank=False, unique=True, editable=True, null=False)

    rdns_mode = IntegerField(
        choices=RDNS_MODE_CHOICES, editable=True, default=RDNS_MODE.DEFAULT
    )

    gateway_ip = GenericIPAddressField(blank=True, editable=True, null=True)

    dns_servers = ArrayField(
        TextField(), blank=True, editable=True, null=True, default=list
    )

    allow_dns = BooleanField(
        editable=True, blank=False, null=False, default=True
    )

    allow_proxy = BooleanField(
        editable=True, blank=False, null=False, default=True
    )

    active_discovery = BooleanField(
        editable=True, blank=False, null=False, default=False
    )

    managed = BooleanField(
        editable=True, blank=False, null=False, default=True
    )

    # MAAS models VLANs by VID, all physical networks which use the same VID
    # share the same VLAN model. Many systems only support network booting on
    # VID 0 making it very likely a user with separate physical networks will
    # use VID 0 across all of them.
    #
    # MAAS currently configures bootloaders in the subnet stanza in dhcpd.conf.
    # To allow disabling boot architectures on seperate physical networks which
    # use the same VID configuration of which boot architectures are disabled
    # is stored on the subnet model.
    disabled_boot_architectures = ArrayField(
        CharField(max_length=64),
        blank=True,
        editable=True,
        null=False,
        default=list,
    )

    def __setattr__(self, name, value):
        if hasattr(self, f"_previous_{name}"):
            setattr(self, f"_previous_{name}", getattr(self, name))
        super().__setattr__(name, value)

    @property
    def label(self):
        """Returns a human-friendly label for this subnet."""
        cidr = str(self.cidr)
        # Note: there is a not-NULL check for the 'name' field, so this only
        # applies to unsaved objects.
        if self.name is None or self.name == "":
            return cidr
        if cidr not in self.name:
            return f"{self.name} ({self.cidr})"
        else:
            return self.name

    @property
    def space(self):
        """Backward compatibility shim to get the space for this subnet."""
        return self.vlan.space

    def get_ipnetwork(self) -> IPNetwork:
        return IPNetwork(self.cidr)

    def get_ip_version(self) -> int:
        return self.get_ipnetwork().version

    def update_cidr(self, cidr):
        cidr = str(cidr)
        # If the old name had the CIDR embedded in it, update that first.
        if self.name:
            self.name = self.name.replace(str(self.cidr), cidr)
        else:
            self.name = cidr
        self.cidr = cidr

    def __str__(self):
        return f"{self.name}:{self.cidr}(vid={self.vlan.vid})"

    def validate_gateway_ip(self):
        if self.gateway_ip is None or self.gateway_ip == "":
            return
        gateway_addr = IPAddress(self.gateway_ip)
        network = self.get_ipnetwork()
        if gateway_addr in network:
            # If the gateway is in the network, it is fine.
            return
        elif network.version == 6 and gateway_addr.is_link_local():
            # If this is an IPv6 network and the gateway is in the link-local
            # network (fe80::/64 -- required to be configured by the spec),
            # then it is also valid.
            return
        else:
            # The gateway is not valid for the network.
            message = "Gateway IP must be within CIDR range."
            raise ValidationError({"gateway_ip": [message]})

    def clean_fields(self, *args, **kwargs):
        # XXX mpontillo 2016-03-16: this function exists due to bug #1557767.
        # This workaround exists to prevent potential unintended consequences
        # of making the name optional.
        if (self.name is None or self.name == "") and self.cidr is not None:
            self.name = str(self.cidr)
        super().clean_fields(*args, **kwargs)

    def validate_cidr(self, exclude_id: int | None):
        if self.cidr:
            with connection.cursor() as cursor:
                params = [self.cidr, self.cidr]
                query = """
                    SELECT EXISTS (
                        SELECT 1
                        FROM maasserver_subnet
                        WHERE
                            (cidr >>= %s OR cidr <<= %s)
                """
                if exclude_id is not None:
                    query += " AND id != %s"
                    params.append(exclude_id)
                query += ")"

                cursor.execute(query, params)
                if cursor.fetchone()[0]:
                    raise ValidationError(
                        f"Subnet {self.cidr} would overlap with existing subnets."
                    )

    def clean(self, *args, **kwargs):
        self.validate_gateway_ip()
        self.validate_cidr(self.id)

    def delete(self, *args, **kwargs):
        from maasserver.models.staticipaddress import FreeIPAddress

        if self.rdns_mode != RDNS_MODE.DISABLED:
            DNSPublication.objects.create_for_config_update(
                source=f"removed subnet {self.cidr}",
                action=DnsUpdateAction.RELOAD,
                zone="",
                label="",
                rtype="",
            )

        # Check if DHCP is enabled on the VLAN this subnet is attached to.
        if self.vlan.dhcp_on and self.get_dynamic_ranges().exists():
            raise ValidationError(
                "Cannot delete a subnet that is actively servicing a dynamic "
                "IP range. (Delete the dynamic range or disable DHCP first.)"
            )
        FreeIPAddress.remove_cache(self)
        vlan_id = self.vlan_id
        dhcp_enabled = self.vlan.dhcp_on
        super().delete(*args, **kwargs)

        if dhcp_enabled:
            post_commit_do(
                start_workflow,
                workflow_name=CONFIGURE_DHCP_WORKFLOW_NAME,
                param=ConfigureDHCPParam(vlan_ids=[vlan_id]),
                task_queue="region",
            )

    def get_allocated_ips(self):
        """Get all the IPs for the given subnets

        Any StaticIPAddress record that has a non-emtpy ip is considered to
        be allocated.

        It returns a generator producing a 2-tuple with the subnet and a
        list of IP tuples

        An IP tuple consist of the IP as a string and its allocation type.

        The result can be cached by calling cache_allocated_ips().
        """
        ips = getattr(self, "_cached_allocated_ips", None)
        if ips is None:
            [(_, ips)] = list(get_allocated_ips([self]))
        return ips

    def cache_allocated_ips(self, ips):
        """Cache the results of get_allocated_ips().

        This is to be used similar to how prefetching objects on
        queryset works.
        """
        self._cached_allocated_ips = ips

    def get_ipranges_in_use(
        self,
    ) -> MAASIPSet:
        """Returns a `MAASIPSet` of `MAASIPRange` objects which are currently
        in use on this `Subnet`.
        """
        return service_layer.services.v3subnet_utilization.get_ipranges_in_use(
            self.id
        )

    def get_ipranges_available_for_reserved_range(
        self, exclude_ip_range_id: int | None = None
    ) -> MAASIPSet:
        return service_layer.services.v3subnet_utilization.get_ipranges_available_for_reserved_range(
            self.id, exclude_ip_range_id
        )

    def get_ipranges_available_for_dynamic_range(
        self, exclude_ip_range_id: int | None = None
    ) -> MAASIPSet:
        return service_layer.services.v3subnet_utilization.get_ipranges_available_for_dynamic_range(
            self.id, exclude_ip_range_id
        )

    def get_ipranges_not_in_use(
        self,
    ) -> MAASIPSet:
        """Returns a `MAASIPSet` of ranges which are currently free on this
        `Subnet`.
        """
        return service_layer.services.v3subnet_utilization.get_free_ipranges(
            self.id
        )

    def get_least_recently_seen_unknown_neighbour(self):
        """
        Returns the least recently seen unknown neighbour or this subnet.

        Useful when allocating an IP address, to safeguard against assigning
        an address another host is still using.

        :return: a `maasserver.models.Discovery` object
        """
        # Circular imports.
        from maasserver.models import Discovery

        # Note: for the purposes of this function, being in part of a "used"
        # range (such as a router IP address or reserved range) makes it
        # "known". So we need to avoid those here in order to avoid stepping
        # on network infrastructure, reserved ranges, etc.
        unused = service_layer.services.v3subnet_utilization.get_free_ipranges(
            subnet_id=self.id
        )
        least_recent_neighbours = (
            Discovery.objects.filter(subnet=self)
            .by_unknown_ip()
            .order_by("last_seen")
        )
        for neighbor in least_recent_neighbours:
            if neighbor.ip in unused:
                return neighbor
        return None

    def get_iprange_usage(self) -> MAASIPSet:
        """Returns both the reserved and unreserved IP ranges in this Subnet.
        (This prevents a potential race condition that could occur if an IP
        address is allocated or deallocated between calls.)

        :returns: A MAASIPSet with the reserved and unreserved ranges.
        """
        return (
            service_layer.services.v3subnet_utilization.get_subnet_utilization(
                self.id
            )
        )

    def get_next_ip_for_allocation(
        self,
        exclude_addresses: Optional[list[str]] = None,
        count: int = 1,
    ) -> Iterable[MaybeIPAddress]:
        """Heuristic to return the "best" address from this subnet to use next.

        :param exclude_addresses: Optional list of addresses to exclude.
        """
        free_ranges = service_layer.services.v3subnet_utilization.get_ipranges_for_ip_allocation(
            subnet_id=self.id,
            exclude_addresses=exclude_addresses,
        )
        if len(free_ranges) == 0:
            # We tried considering neighbours as "in-use" addresses, but the
            # subnet is still full. So make an educated guess about which IP
            # address is least likely to be in-use.
            discovery = self.get_least_recently_seen_unknown_neighbour()
            if discovery is not None:
                maaslog.warning(
                    "Next IP address to allocate from '%s' has been observed "
                    "previously: %s was last claimed by %s via %s at %s."
                    % (
                        self.label,
                        discovery.ip,
                        discovery.mac_address,
                        discovery.observer_interface.get_log_string(),
                        discovery.last_seen,
                    )
                )
                # TODO: this must return `count` IPs
                return [str(discovery.ip)]
            else:
                raise StaticIPAddressExhaustion(
                    "No more IPs available in subnet: %s." % self.cidr
                )
        # The purpose of this is to that we ensure we always get an IP address
        # from the *smallest* free contiguous range. This way, larger ranges
        # can be preserved in case they need to be used for applications
        # requiring them. If two ranges have the same number of IPs, choose the
        # lowest one.
        free_ips = []
        while count > 0 and len(free_ranges) > 0:
            free_range = min(
                free_ranges, key=attrgetter("num_addresses", "first")
            )
            avail = min(count, free_range.num_addresses)
            for i in range(avail):
                free_ips.append(str(IPAddress(free_range.first + i)))
            free_ranges.discard(free_range)
            count -= avail
        return free_ips

    def render_json_for_related_ips(
        self, with_username: bool = True, with_summary: bool = True
    ) -> list:
        """Render a representation of this subnet's related IP addresses,
        suitable for converting to JSON. Optionally exclude user and node
        information."""
        ip_addresses = self.staticipaddress_set.all()
        if with_username:
            ip_addresses = ip_addresses.prefetch_related("user")
        if with_summary:
            ip_addresses = ip_addresses.prefetch_related(
                "interface_set",
                "interface_set__node_config__node__domain",
                "bmc_set__node_set",
                "dnsresource_set__domain",
            )
        return sorted(
            (
                ip.render_json(
                    with_username=with_username, with_summary=with_summary
                )
                for ip in ip_addresses
                if ip.ip
            ),
            key=lambda json: IPAddress(json["ip"]),
        )

    def get_dynamic_ranges(self):
        return self.iprange_set.filter(type=IPRANGE_TYPE.DYNAMIC)

    def get_reserved_ranges(self):
        return self.iprange_set.filter(type=IPRANGE_TYPE.RESERVED)

    def is_valid_static_ip(self, *args, **kwargs):
        """Validates that the requested IP address is acceptable for allocation
        in this `Subnet` (assuming it has not already been allocated).

        Returns `True` if the IP address is acceptable, and `False` if not.

        Does not consider whether or not the IP address is already allocated,
        only whether or not it is in the proper network and range.

        :return: bool
        """
        try:
            self.validate_static_ip(*args, **kwargs)
        except MAASAPIException:
            return False
        return True

    def validate_static_ip(
        self, ip, restrict_ip_to_unreserved_ranges: bool = True
    ):
        """Validates that the requested IP address is acceptable for allocation
        in this `Subnet` (assuming it has not already been allocated).

        Raises `StaticIPAddressUnavailable` if the address is not acceptable.

        Does not consider whether or not the IP address is already allocated,
        only whether or not it is in the proper network and range.

        :raises StaticIPAddressUnavailable: If the IP address specified is not
            available for allocation.
        """
        if ip not in self.get_ipnetwork():
            raise StaticIPAddressOutOfRange(
                f"{ip} is not within subnet CIDR: {self.cidr}"
            )
        for iprange in self.get_dynamic_maasipset():
            if ip in iprange:
                raise StaticIPAddressUnavailable(
                    "%s is within the dynamic range from %s to %s"
                    % (ip, IPAddress(iprange.first), IPAddress(iprange.last))
                )
        if restrict_ip_to_unreserved_ranges:
            for iprange in self.get_reserved_maasipset():
                if ip in iprange:
                    raise StaticIPAddressUnavailable(
                        "%s is within the reserved range from %s to %s"
                        % (
                            ip,
                            IPAddress(iprange.first),
                            IPAddress(iprange.last),
                        )
                    )

    def get_reserved_maasipset(self, exclude_ip_ranges: list = None):
        if exclude_ip_ranges is None:
            exclude_ip_ranges = []
        reserved_ranges = MAASIPSet(
            iprange.get_MAASIPRange()
            for iprange in self.iprange_set.all()
            if iprange.type == IPRANGE_TYPE.RESERVED
            and iprange not in exclude_ip_ranges
        )
        return reserved_ranges

    def get_dynamic_maasipset(self, exclude_ip_ranges: list = None):
        if exclude_ip_ranges is None:
            exclude_ip_ranges = []
        dynamic_ranges = MAASIPSet(
            iprange.get_MAASIPRange()
            for iprange in self.iprange_set.all()
            if iprange.type == IPRANGE_TYPE.DYNAMIC
            and iprange not in exclude_ip_ranges
        )
        return dynamic_ranges

    def get_dynamic_range_for_ip(self, ip):
        """Return `IPRange` for the provided `ip`."""
        # XXX mpontillo 2016-01-21: for some reason this query doesn't work.
        # I tried it both like this, and with:
        #     start_ip__gte=ip, and end_ip__lte=ip
        # return get_one(self.get_dynamic_ranges().extra(
        #        where=["start_ip >= inet '%s'" % ip,
        # ... which sounds a lot like comment 15 in:
        #     https://code.djangoproject.com/ticket/11442
        for iprange in self.get_dynamic_ranges():
            if ip in iprange.netaddr_iprange:
                return iprange
        return None

    def update_allocation_notification(self):
        # Workaround for edge cases in Django. (See bug #1702527.)
        if self.id is None:
            return
        ident = "ip_exhaustion__subnet_%d" % self.id
        # Circular imports.
        from maasserver.models import Config, Notification

        threshold = Config.objects.get_config(
            "subnet_ip_exhaustion_threshold_count"
        )
        notification = Notification.objects.filter(ident=ident).first()
        delete_notification = False
        if threshold > 0:
            full_iprange = self.get_iprange_usage()
            statistics = IPRangeStatistics(full_iprange)
            # Check if there are less available IPs in the subnet than the
            # warning threshold.
            meets_warning_threshold = statistics.num_available <= threshold
            # Check if the warning threshold is appropriate relative to the
            # size of the subnet. It's pointless to warn about address
            # exhaustion on a /30, for example: the admin already knows it's
            # small, so we would just be annoying them.
            subnet_is_reasonably_large_relative_to_threshold = (
                threshold * 3 <= statistics.total_addresses
            )
            if (
                meets_warning_threshold
                and subnet_is_reasonably_large_relative_to_threshold
            ):
                notification_text = (
                    "IP address exhaustion imminent on subnet: %s. "
                    "There are %d free addresses out of %d "
                    "(%s used)."
                ) % (
                    self.label,
                    statistics.num_available,
                    statistics.total_addresses,
                    statistics.usage_percentage_string,
                )
                if notification is None:
                    Notification.objects.create_warning_for_admins(
                        notification_text, ident=ident
                    )
                else:
                    # Note: This will update the notification, but will not
                    # bring it back for those who have dismissed it. Maybe we
                    # should consider creating a new notification if the
                    # situation is now more severe, such as raise it to an
                    # error if it's half remaining threshold.
                    notification.message = notification_text
                    notification.save()
            else:
                delete_notification = True
        else:
            delete_notification = True
        if notification is not None and delete_notification:
            notification.delete()

    def save(self, *args, **kwargs):
        if self.id is None and self.rdns_mode != RDNS_MODE.DISABLED:
            DNSPublication.objects.create_for_config_update(
                source=f"added subnet {self.cidr}",
                action=DnsUpdateAction.RELOAD,
                zone="",
                label="",
                rtype="",
            )
        else:
            # each change creates a new dnspublication
            if self._previous_cidr and self._previous_cidr != self.cidr:
                DNSPublication.objects.create_for_config_update(
                    source=f"subnet {self._previous_cidr} changed to {self.cidr}",
                    action=DnsUpdateAction.RELOAD,
                    zone="",
                    label="",
                    rtype="",
                )
            if (
                self._previous_rdns_mode is not None
                and self._previous_rdns_mode != self.rdns_mode
            ):
                DNSPublication.objects.create_for_config_update(
                    source=f"subnet {self.cidr} rdns changed to {self.rdns_mode}",
                    action=DnsUpdateAction.RELOAD,
                    zone="",
                    label="",
                    rtype="",
                )
            if (
                self._previous_allow_dns is not None
                and self._previous_allow_dns != self.allow_dns
            ):
                DNSPublication.objects.create_for_config_update(
                    source=f"subnet {self.cidr} allow_dns changed to {self.allow_dns}",
                    action=DnsUpdateAction.RELOAD,
                    zone="",
                    label="",
                    rtype="",
                )

        super().save(*args, **kwargs)

        param = ConfigureDHCPParam(subnet_ids=[self.id])
        if self._previous_vlan_id and self._previous_vlan_id != self.vlan_id:
            param.vlan_ids = [self._previous_vlan_id]  # handle moving VLANs

        if self.vlan.dhcp_on or (
            self._previous_vlan_id and self._previous_vlan_id != self.vlan_id
        ):
            post_commit_do(
                start_workflow,
                workflow_name=CONFIGURE_DHCP_WORKFLOW_NAME,
                param=param,
                task_queue="region",
            )


def get_allocated_ips(subnets):
    """Get all the IPs for the given subnets

    Any StaticIPAddress record that has a non-emtpy ip is considered to
    be allocated.

    It returns a generator producing a 2-tuple with the subnet and a
    list of IP tuples

    An IP tuple consist of the IP as a string and its allocation type.
    """
    from maasserver.models.staticipaddress import StaticIPAddress

    mapping = {subnet.id: [] for subnet in subnets}
    ips = StaticIPAddress.objects.filter(
        subnet__id__in=mapping.keys(), ip__isnull=False
    )
    for subnet_id, ip, alloc_type in ips.values_list(
        "subnet_id", "ip", "alloc_type"
    ):
        mapping[subnet_id].append((ip, alloc_type))
    for subnet in subnets:
        yield subnet, mapping[subnet.id]


def get_dhcp_vlan(vlan):
    if vlan is None:
        return None
    dhcp_vlan = vlan if vlan.relay_vlan_id is None else vlan.relay_vlan
    if not dhcp_vlan.dhcp_on or dhcp_vlan.primary_rack is None:
        return None
    return dhcp_vlan


def get_boot_rackcontroller_ips(subnet):
    """Get the IPs of the rack controller a machine can boot from.

    The subnet is where the machine has an IP from. It returns all the IPs
    that might be suitable, but it will sort them with the most suitable
    IPs first.

    It prefers rack controller IPs from the same subnet and the same
    IP family (ipv4/ipv6).

    If there's a DHCP relay in place, we don't know which rack controller
    IP is the best one, since it proably won't have an IP on the same subnet
    as the booting machine. In that case, we put any of the IPs that are
    on the VLAN that serves DHCP and assumes that it's routable.
    """

    def rank_ip(ip):
        ip = IPAddress(ip)
        network = IPNetwork(subnet.cidr)
        value = 2
        if ip in network:
            value = 1
        return value

    from maasserver.models.staticipaddress import StaticIPAddress

    dhcp_vlan = None
    if subnet is not None:
        dhcp_vlan = get_dhcp_vlan(subnet.vlan)
    if dhcp_vlan is None:
        return []

    node_configs = [dhcp_vlan.primary_rack.current_config_id]
    if dhcp_vlan.secondary_rack:
        node_configs.append(dhcp_vlan.secondary_rack.current_config_id)
    static_ips = StaticIPAddress.objects.filter(
        ~Q(alloc_type=IPADDRESS_TYPE.DISCOVERED),
        ~Q(ip__isnull=True),
        subnet__vlan=dhcp_vlan,
        interface__node_config__in=node_configs,
    )
    ip_version = IPNetwork(subnet.cidr).version
    ips = sorted(
        (
            static_ip.ip
            for static_ip in static_ips
            if IPAddress(static_ip.ip).version == ip_version
        ),
        key=rank_ip,
    )
    return ips
