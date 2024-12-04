# Copyright 2012-2017 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Custom model and form fields."""

from itertools import chain
import re
import urllib

from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import RegexValidator, URLValidator
from django.db import connections
from django.db.models import (
    CharField,
    Field,
    GenericIPAddressField,
    IntegerField,
    Q,
    URLField,
)
from django.utils.deconstruct import deconstructible
from django.utils.encoding import force_str
from netaddr import AddrFormatError, IPAddress, IPNetwork

from maasserver.models.versionedtextfile import VersionedTextFile
from maasserver.utils.converters import parse_systemd_interval
from maasserver.utils.dns import validate_domain_name, validate_hostname
from maasserver.utils.orm import get_one, validate_in_transaction

# Validator for the name attribute of model entities.
MODEL_NAME_VALIDATOR = RegexValidator(r"^\w[ \w-]*$")

HOSTNAME_RE = r"((([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9\.]))+([A-Za-z]|[A-Za-z][A-Za-z0-9\-]*[A-Za-z0-9]))"
IPV4_RE = r"((?:0|25[0-5]|2[0-4]\d|1\d?\d?|[1-9]\d?)(?:\.(?:0|25[0-5]|2[0-4]\d|1\d?\d?|[1-9]\d?)){3})"
IPV6_RE = (
    rf"((?:\[)?([a-f0-9:]{{1,4}}:+)+(([a-f0-9]{{1,4}}(?:\])?)|{IPV4_RE}))"
)

# supported input MAC formats
MAC_FIELD_RE = re.compile(
    r"^"
    r"([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}|"  # aa:bb:cc:dd:ee:ff
    r"([0-9a-fA-F]{1,2}-){5}[0-9a-fA-F]{1,2}|"  # aa-bb-cc-dd-ee-ff
    r"([0-9a-fA-F]{3,4}.){2}[0-9a-fA-F]{3,4}"  # aabb.ccdd.eeff
    r"$"
)
# MAC format for DB storage
MAC_RE = re.compile(r"^([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}$")

MAC_FIELD_VALIDATOR = RegexValidator(
    regex=MAC_FIELD_RE, message="'%(value)s' is not a valid MAC address."
)
# validate that the MAC is in the expected format for DB storage
# (colon-separated)
MAC_VALIDATOR = RegexValidator(
    regex=MAC_RE, message="'%(value)s' is not a valid MAC address."
)
MAC_SPLIT_RE = re.compile(r"[-:.]")

# Remote virsh uris general form:
# driver[+transport]://[username@][hostname][:port]/[path][?extraparameters]
VIRSH_ADDR_RE = re.compile(
    r"^"
    r"(((xen|qemu|test)"  # driver
    r"(?:\+\w+)?"  # +transport
    r"://"
    r"(?:\w+@)?"  # username@
    rf"(?:{HOSTNAME_RE}|"  # hostname, or
    rf"{IPV4_RE}|"  # ipv4, or
    rf"{IPV6_RE})?"  # ipv6
    r"(?::\d{2,5})?"  # :port
    r"(?:[/?][^\s]*)?)"  # path + parameters
    r"|"
    rf"{IPV4_RE}"  # could also be only a ipv4/ipv6 address
    rf"|{IPV6_RE})"
    r"$"
)

VIRSH_ADDR_FIELD_VALIDATOR = RegexValidator(
    regex=VIRSH_ADDR_RE, message="Enter a valid virsh address."
)


LXD_ADDR_RE = re.compile(
    r"^"
    r"(?:(http|https)://)?"
    rf"({HOSTNAME_RE}|"  # hostname, or
    rf"{IPV4_RE}|"  # ipv4, or
    rf"{IPV6_RE})"  # ipv6
    r"(?::\d{2,5})?"  # port
    r"$"
)

LXD_ADDR_FIELD_VALIDATOR = RegexValidator(
    regex=LXD_ADDR_RE, message="Enter a valid LXD address."
)


def normalise_macaddress(mac: str) -> str:
    """Return a colon-separated format for the specified MAC.

    This supports converting from input formats matching the MAC_FIELD_RE
    regexp.

    """

    tokens = MAC_SPLIT_RE.split(mac.lower())
    match len(tokens):
        case 1:  # no separator
            tokens = re.findall("..", tokens[0])
        case 3:  # each token is two bytes
            tokens = chain(
                *(re.findall("..", token.zfill(4)) for token in tokens)
            )
        case _:  # single-byte tokens
            tokens = (token.zfill(2) for token in tokens)
    return ":".join(tokens)


class MACAddressFormField(forms.CharField):
    """Form field type: MAC address."""

    def validate(self, value):
        if value:
            MAC_FIELD_VALIDATOR(value)

    def clean(self, value):
        value = super().clean(value)
        return normalise_macaddress(value)


class XMLField(Field):
    """A field for storing xml natively.

    This is not like the removed Django XMLField which just added basic python
    level checking on top of a text column.

    Really inserts should be wrapped like `XMLPARSE(DOCUMENT value)` but it's
    hard to do from django so rely on postgres supporting casting from char.
    """

    description = "XML document or fragment"

    def db_type(self, connection):
        return "xml"


class LargeObjectFile:
    """Large object file.

    Proxy the access from this object to psycopg2.
    """

    def __init__(self, oid=0, field=None, instance=None, block_size=(1 << 16)):
        self.oid = oid
        self.field = field
        self.instance = instance
        self.block_size = block_size
        self._lobject = None

    def __getattr__(self, name):
        if self._lobject is None:
            raise OSError("LargeObjectFile is not opened.")
        return getattr(self._lobject, name)

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def __iter__(self):
        return self

    def write(self, data: bytes):
        """Write `data` to the underlying large object.

        This exists so that type annotations can be enforced.
        """
        self._lobject.write(data)

    def open(
        self, mode="rwb", new_file=None, using="default", connection=None
    ):
        """Opens the internal large object instance."""
        if "b" not in mode:
            raise ValueError("Large objects must be opened in binary mode.")
        if connection is None:
            connection = connections[using]
        validate_in_transaction(connection)
        self._lobject = connection.connection.lobject(
            self.oid, mode, 0, new_file
        )
        self.oid = self._lobject.oid
        return self

    def unlink(self):
        """Removes the large object."""
        if self._lobject is None:
            # Need to open the lobject so we get a reference to it in the
            # database, to perform the unlink.
            self.open()
            self.close()
        self._lobject.unlink()
        self._lobject = None
        self.oid = 0

    def __next__(self):
        r = self.read(self.block_size)
        if len(r) == 0:
            raise StopIteration
        return r


class LargeObjectDescriptor:
    """LargeObjectField descriptor."""

    def __init__(self, field):
        self.field = field

    def __get__(self, instance, type=None):
        if instance is None:
            return self
        return instance.__dict__[self.field.name]

    def __set__(self, instance, value):
        value = self.field.to_python(value)
        if value is not None:
            if not isinstance(value, LargeObjectFile):
                value = LargeObjectFile(value, self.field, instance)
        instance.__dict__[self.field.name] = value


class LargeObjectField(IntegerField):
    """A field that stores large amounts of data into postgres large object
    storage.

    Internally the field on the model is an `oid` field, that returns a proxy
    to the referenced large object.
    """

    def __init__(self, *args, **kwargs):
        self.block_size = kwargs.pop("block_size", 1 << 16)
        super().__init__(*args, **kwargs)

    @property
    def validators(self):
        # No validation. IntegerField will add incorrect validation. This
        # removes that validation.
        return []

    def db_type(self, connection):
        """Returns the database column data type for LargeObjectField."""
        # oid is the column type postgres uses to reference a large object
        return "oid"

    def contribute_to_class(self, cls, name):
        """Set the descriptor for the large object."""
        super().contribute_to_class(cls, name)
        setattr(cls, self.name, LargeObjectDescriptor(self))

    def get_db_prep_value(self, value, connection=None, prepared=False):
        """python -> db: `oid` value"""
        if value is None:
            return None
        if isinstance(value, LargeObjectFile):
            if value.oid > 0:
                return value.oid
            raise AssertionError(
                "LargeObjectFile's oid must be greater than 0."
            )
        raise AssertionError(
            "Invalid LargeObjectField value (expected LargeObjectFile): '%s'"
            % repr(value)
        )

    def to_python(self, value):
        """db -> python: `LargeObjectFile`"""
        if value is None:
            return None
        elif isinstance(value, LargeObjectFile):
            return value
        elif isinstance(value, int):
            return LargeObjectFile(value, self, self.model, self.block_size)
        raise AssertionError(
            "Invalid LargeObjectField value (expected integer): '%s'"
            % repr(value)
        )


class CIDRField(Field):
    description = "PostgreSQL CIDR field"

    def parse_cidr(self, value):
        try:
            return str(IPNetwork(value).cidr)
        except AddrFormatError as e:
            raise ValidationError(str(e)) from e

    def db_type(self, connection):
        return "cidr"

    def get_prep_value(self, value):
        if value is None or value == "":
            return None
        return self.parse_cidr(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self.parse_cidr(value)

    def to_python(self, value):
        if value is None or value == "":
            return None
        if isinstance(value, IPNetwork):
            return str(value)
        if not value:
            return value
        return self.parse_cidr(value)

    def formfield(self, **kwargs):
        defaults = {"form_class": forms.CharField}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class IPv4CIDRField(CIDRField):
    """IPv4-only CIDR"""

    def get_prep_value(self, value):
        if value is None or value == "":
            return None
        return self.to_python(value)

    def to_python(self, value):
        if value is None or value == "":
            return None
        else:
            try:
                cidr = IPNetwork(value)
            except AddrFormatError:
                raise ValidationError(
                    "Invalid network: %(cidr)s", params={"cidr": value}
                )
            if cidr.cidr.version != 4:
                raise ValidationError(
                    "%(cidr)s: Only IPv4 networks supported.",
                    params={"cidr": value},
                )
        return str(cidr.cidr)


class IPListFormField(forms.CharField):
    """Accepts a space/comma separated list of IP addresses.

    This field normalizes the list to a space-separated list.
    """

    separators = re.compile(r"[,\s]+")

    def clean(self, value):
        if value is None:
            return None
        else:
            ips = re.split(self.separators, value)
            ips = [ip.strip() for ip in ips if ip != ""]
            for ip in ips:
                try:
                    GenericIPAddressField().clean(ip, model_instance=None)
                except ValidationError:
                    raise ValidationError(
                        "Invalid IP address: %s; provide a list of "
                        "space-separated IP addresses" % ip
                    )
            return " ".join(ips)


class IPPortListFormField(IPListFormField):
    def __init__(self, default_port=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._default_port = default_port

    def clean(self, value):
        if value is None:
            return None
        else:
            ip_ports = re.split(self.separators, value)
            ip_ports = [
                ip_port.strip() for ip_port in ip_ports if ip_ports != ""
            ]
            result = []
            for ip_port in ip_ports:
                if "." in ip_port or ("[" == ip_port[0] and "]:" in ip_port):
                    sock_addr = urllib.parse.urlsplit("//" + ip_port)
                    ip = sock_addr.hostname
                    port = (
                        int(sock_addr.port)
                        if sock_addr.port
                        else self._default_port
                    )
                else:
                    ip = ip_port
                    port = self._default_port
                try:
                    GenericIPAddressField().clean(ip, model_instance=None)
                    IntegerField().clean(port, model_instance=None)
                except ValidationError:
                    raise ValidationError(
                        f"Invalid IP and port combination: {ip_port};"
                        f"please provide a list of space-separated IP addresses {'and port' if not self._default_port else ''}"
                    )
                result.append((ip, port))
        return result


class HostListFormField(forms.CharField):
    """Accepts a space/comma separated list of hostnames or IP addresses.

    This field normalizes the list to a space-separated list.
    """

    separators = re.compile(r"[,\s]+")

    # Regular expressions to sniff out things that look like IP addresses;
    # additional and more robust validation ought to be done to make sure.
    pt_ipv4 = r"(?: \d{1,3} [.] \d{1,3} [.] \d{1,3} [.] \d{1,3} )"
    pt_ipv6 = r"(?: (?: [\da-fA-F]+ :+)+ (?: [\da-fA-F]+ | %s )+ )" % pt_ipv4
    pt_ip = re.compile(rf"^ (?: {pt_ipv4} | {pt_ipv6} ) $", re.VERBOSE)

    def clean(self, value):
        if value is None:
            return None
        else:
            values = map(str.strip, self.separators.split(value))
            values = (value for value in values if len(value) != 0)
            values = map(self._clean_addr_or_host, values)
            return " ".join(values)

    def _clean_addr_or_host(self, value):
        looks_like_ip = self.pt_ip.match(value) is not None
        if looks_like_ip:
            return self._clean_addr(value)
        elif ":" in value:
            # This is probably an IPv6 address. It's definitely not a
            # hostname.
            return self._clean_addr(value)
        else:
            return self._clean_host(value)

    def _clean_addr(self, addr):
        try:
            addr = IPAddress(addr)
        except AddrFormatError as error:
            message = str(error)  # netaddr has good messages.
            message = message[:1].upper() + message[1:] + "."
            raise ValidationError(message)
        else:
            return str(addr)

    def _clean_host(self, host):
        try:
            validate_hostname(host)
        except ValidationError as error:
            raise ValidationError("Invalid hostname: " + error.message)
        else:
            return host


class SubnetListFormField(forms.CharField):
    """Accepts a space/comma separated list of hostnames, Subnets or IPs.

    This field normalizes the list to a space-separated list.
    """

    separators = re.compile(r"[,\s]+")

    # Regular expressions to sniff out things that look like IP addresses;
    # additional and more robust validation ought to be done to make sure.
    pt_ipv4 = r"(?: \d{1,3} [.] \d{1,3} [.] \d{1,3} [.] \d{1,3} )"
    pt_ipv6 = r"(?: (|[0-9A-Fa-f]{1,4}) [:] (|[0-9A-Fa-f]{1,4}) [:] (.*))"
    pt_ip = re.compile(rf"^ (?: {pt_ipv4} | {pt_ipv6} ) $", re.VERBOSE)
    pt_subnet = re.compile(
        rf"^ (?: {pt_ipv4} | {pt_ipv6} ) \/\d+$", re.VERBOSE
    )

    def clean(self, value):
        if value is None:
            return None
        else:
            values = map(str.strip, self.separators.split(value))
            values = (value for value in values if len(value) != 0)
            values = map(self._clean_addr_or_host, values)
            return " ".join(values)

    def _clean_addr_or_host(self, value):
        looks_like_ip = self.pt_ip.match(value) is not None
        looks_like_subnet = self.pt_subnet.match(value) is not None
        if looks_like_subnet:
            return self._clean_subnet(value)
        elif looks_like_ip:
            return self._clean_addr(value)
        else:
            return self._clean_host(value)

    def _clean_addr(self, value):
        try:
            addr = IPAddress(value)
        except ValueError:
            return
        except AddrFormatError:
            raise ValidationError("Invalid IP address: %s." % value)
        else:
            return str(addr)

    def _clean_subnet(self, value):
        try:
            cidr = IPNetwork(value)
        except AddrFormatError:
            raise ValidationError("Invalid network: %s." % value)
        else:
            return str(cidr)

    def _clean_host(self, host):
        try:
            validate_hostname(host)
        except ValidationError as error:
            raise ValidationError("Invalid hostname: " + error.message)
        else:
            return host


class CaseInsensitiveChoiceField(forms.ChoiceField):
    """ChoiceField that allows the input to be case insensitive."""

    def to_python(self, value):
        if value not in self.empty_values:
            value = value.lower()
        return super().to_python(value)


class SpecifierOrModelChoiceField(forms.ModelChoiceField):
    """ModelChoiceField which is also able to accept input in the format
    of a specifiers string.
    """

    def to_python(self, value):
        try:
            return super().to_python(value)
        except ValidationError as e:
            if isinstance(value, str):
                object_id = self.queryset.get_object_id(value)
                if object_id is None:
                    obj = get_one(
                        self.queryset.filter_by_specifiers(value),
                        exception_class=ValidationError,
                    )
                    if obj is not None:
                        return obj
                else:
                    try:
                        return self.queryset.get(id=object_id)
                    except ObjectDoesNotExist:
                        # Re-raising this as a ValidationError prevents the API
                        # from returning an internal server error rather than
                        # a bad request.
                        raise ValidationError("None found with id=%s." % value)
            raise e


class DomainNameField(CharField):
    """Custom Django field that strips whitespace and trailing '.' characters
    from DNS domain names before validating and saving to the database. Also,
    validates that the domain name is valid according to RFCs 952 and 1123.
    (Note that this field type should NOT be used for hostnames, since the set
    of valid hostnames is smaller than the set of valid domain names.)
    """

    def __init__(self, *args, **kwargs):
        validators = kwargs.pop("validators", [])
        validators.append(validate_domain_name)
        kwargs["validators"] = validators
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["validators"]
        return name, path, args, kwargs

    # Here we are using (abusing?) the to_python() function to coerce and
    # normalize this type. Django does not have a function intended purely
    # to normalize before saving to the database, so to_python() is the next
    # closest alternative. For more information, see:
    # https://docs.djangoproject.com/en/1.6/ref/forms/validation/
    # https://code.djangoproject.com/ticket/6362
    def to_python(self, value):
        value = super().to_python(value)
        if value is None:
            return None
        value = value.strip().rstrip(".")
        return value


class NodeChoiceField(forms.ModelChoiceField):
    def __init__(self, queryset, *args, **kwargs):
        super().__init__(queryset=queryset.distinct(), *args, **kwargs)

    def clean(self, value):
        if not value:
            return None
        # Avoid circular imports
        from maasserver.models.node import Node

        if isinstance(value, Node):
            if value not in self.queryset:
                raise ValidationError(
                    "Select a valid choice. "
                    "%s is not one of the available choices." % value.system_id
                )
            return value

        try:
            return self.queryset.get(Q(system_id=value) | Q(hostname=value))
        except Node.DoesNotExist:
            raise ValidationError(
                "Select a valid choice. "
                "%s is not one of the available choices." % value
            )

    def to_python(self, value):
        # Avoid circular imports
        from maasserver.models.node import Node

        try:
            return self.queryset.get(Q(system_id=value) | Q(hostname=value))
        except Node.DoesNotExist:
            raise ValidationError(
                "Select a valid choice. "
                "%s is not one of the available choices." % value
            )


class VersionedTextFileField(forms.ModelChoiceField):
    def __init__(self, *args, **kwargs):
        super().__init__(queryset=None, *args, **kwargs)

    def clean(self, value):
        if self.initial is None:
            if value is None:
                raise ValidationError("Must be given a value")
            # Create a new VersionedTextFile if one doesn't exist
            if isinstance(value, dict):
                return VersionedTextFile.objects.create(**value)
            else:
                return VersionedTextFile.objects.create(data=value)
        elif value is None:
            return self.initial
        else:
            # Create and return a new VersionedTextFile linked to the previous
            # VersionedTextFile
            if isinstance(value, dict):
                return self.initial.update(**value)
            else:
                return self.initial.update(value)


@deconstructible
class URLOrPPAValidator(URLValidator):
    message = "Enter a valid repository URL or PPA location."

    ppa_re = (
        r"ppa:" + URLValidator.hostname_re + r"/" + URLValidator.hostname_re
    )

    def __call__(self, value):
        match = re.search(URLOrPPAValidator.ppa_re, force_str(value))
        # If we don't have a PPA location, let URLValidator do its job.
        if not match:
            super().__call__(value)


class URLOrPPAFormField(forms.URLField):
    widget = forms.URLInput
    default_error_messages = {
        "invalid": "Enter a valid repository URL or PPA location."
    }
    default_validators = [URLOrPPAValidator()]

    def to_python(self, value):
        # Call grandparent method (CharField) to get string value.
        value = super(forms.URLField, self).to_python(value)
        # If it's a PPA locator, return it, else run URL pythonator.
        match = re.search(URLOrPPAValidator.ppa_re, value)
        return value if match else super().to_python(value)


class URLOrPPAField(URLField):
    default_validators = [URLOrPPAValidator()]
    description = "URLOrPPAField"

    # Copied from URLField, with modified form_class.
    def formfield(self, **kwargs):
        defaults = {"form_class": URLOrPPAFormField}
        defaults.update(kwargs)
        return super(URLField, self).formfield(**defaults)


class SystemdIntervalField(forms.CharField):
    def clean(self, value):
        try:
            parse_systemd_interval(value)
        except ValueError as e:
            raise ValidationError(
                f"{e}: {value}, only 'h|hr|hour|hours, m|min|minute|minutes, s|sec|second|seconds' are valid units"
            )
        else:
            return value


class VirshAddressField(forms.CharField):
    """Virsh address form field"""

    def validate(self, value):
        if value:
            VIRSH_ADDR_FIELD_VALIDATOR(value)

    def clean(self, value):
        return super().clean(value)


class LXDAddressField(forms.CharField):
    """LXD address form field"""

    def validate(self, value):
        if value:
            LXD_ADDR_FIELD_VALIDATOR(value)

    def clean(self, value):
        return super().clean(value)


class IPWithOptionalPort(forms.CharField):
    def validate(self, value):
        # try ipv4/ipv6 address without port
        try:
            GenericIPAddressField().clean(value, model_instance=None)
            return value
        except ValidationError:
            pass

        # if it fails, try with port
        try:
            ip, port = value.rsplit(":", maxsplit=1)
            GenericIPAddressField().clean(ip, model_instance=None)
            port = int(port)
            if port < 0 or port > 65535:
                raise ValueError()
            return value
        except (ValueError, ValidationError):
            raise ValidationError(
                message="Invalid IPv4/IPv6 address with optional port."
            )

    def clean(self, value):
        return super().clean(value)
