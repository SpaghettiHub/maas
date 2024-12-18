#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

# Auth
UNEXISTING_USER_OR_INVALID_CREDENTIALS_VIOLATION_TYPE = (
    "UnexistingUserOrInvalidCredentialsViolation"
)
INVALID_TOKEN_VIOLATION_TYPE = "InvalidTokenViolation"
MISSING_PERMISSIONS_VIOLATION_TYPE = "MissingPermissionViolation"
NOT_AUTHENTICATED_VIOLATION_TYPE = "NotAuthenticatedViolation"
USER_EXTERNAL_VALIDATION_FAILED = "UserExternalValidationFailed"

# Fabrics
CANNOT_DELETE_DEFAULT_FABRIC_VIOLATION_TYPE = (
    "CannotDeleteDefaultFabricViolation"
)
CANNOT_DELETE_FABRIC_WITH_SUBNETS_VIOLATION_TYPE = (
    "CannotDeleteFabricWithSubnetsViolation"
)
CANNOT_DELETE_FABRIC_WITH_CONNECTED_INTERFACE_VIOLATION_TYPE = (
    "CannotDeleteFabricWithConnectedInterfacesViolation"
)

# Generic
UNIQUE_CONSTRAINT_VIOLATION_TYPE = "UniqueConstraintViolation"
ETAG_PRECONDITION_VIOLATION_TYPE = "EtagPreconditionViolation"
UNEXISTING_RESOURCE_VIOLATION_TYPE = "UnexistingResourceViolation"
INVALID_ARGUMENT_VIOLATION_TYPE = "InvalidArgumentViolation"
PRECONDITION_FAILED = "PreconditionFailed"

# VLANs
CANNOT_DELETE_DEFAULT_FABRIC_VLAN_VIOLATION_TYPE = (
    "CannotDeleteDefaultFabricVlanViolation"
)
MISSING_DYNAMIC_RANGE_VIOLATION_TYPE = "MissingDynamicRangeViolation"

# Zones
CANNOT_DELETE_DEFAULT_ZONE_VIOLATION_TYPE = "CannotDeleteDefaultZoneViolation"
