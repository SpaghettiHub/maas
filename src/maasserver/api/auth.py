# Copyright 2012-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OAuth authentication for the various APIs."""

from dataclasses import dataclass
from enum import Enum
from itertools import chain
from operator import xor

from django.test.client import WSGIRequest
from piston3.authentication import OAuthAuthentication, send_oauth_error
from piston3.oauth import OAuthError, OAuthMissingParam
from piston3.utils import rc

from maasserver.exceptions import MAASAPIBadRequest, Unauthorized
from maasserver.macaroon_auth import (
    MacaroonAPIAuthentication,
    validate_user_external_auth,
)
from maasserver.models.user import SYSTEM_USERS


class OAuthBadRequest(MAASAPIBadRequest):
    """BadRequest error for OAuth signed requests with invalid parameters."""

    def __init__(self, error):
        super().__init__()
        self.error = error
        self.error.message = f"Bad Request: {error.message}"

    def __str__(self):
        return repr(self.error.message)


class OAuthUnauthorized(Unauthorized):
    """Unauthorized error for OAuth signed requests with invalid tokens."""

    def __init__(self, error):
        super().__init__()
        self.error = error
        # When the error is an authentication error, use a more
        # user-friendly error message.
        if error.message == "Invalid consumer.":
            self.error.message = "Authorization Error: Invalid API key."
        else:
            self.error.message = "Authorization Error: %r" % error.message

    def make_http_response(self):
        return send_oauth_error(self.error)

    def __str__(self):
        return repr(self.error.message)


class ParamIssue(str, Enum):
    MISSING = "missing"
    UNEXPECTED_TYPE = "unexpected type"


@dataclass(slots=True)
class RequestValidityReport:
    problematic_auth_params: dict[str, ParamIssue]
    problematic_get_params: dict[str, ParamIssue]
    problematic_post_params: dict[str, ParamIssue]

    def represents_valid_request(self) -> bool:
        "Determines whether there is _some_ method that can be used."
        return not (
            # The below means that there is a problem in _every_ one
            # of the attempts. We want to be lenient and allow
            # one to take "overwrite" the others if it is valid.
            self.problematic_auth_params
            and self.problematic_get_params
            and self.problematic_post_params
        )

    def contains_invalid_type_issues(self) -> bool:
        return any(
            problem == ParamIssue.UNEXPECTED_TYPE
            for problem in chain(
                self.problematic_auth_params.values(),
                self.problematic_get_params.values(),
                self.problematic_post_params.values(),
            )
        )

    def generate_error_message(self) -> str:
        """Generates an error message showing problematic parameters.

        Should only be used if `is_request_valid` returns false. For safety, we
        make this return an empty string in case `is_request_valid` is True.
        """
        if self.represents_valid_request():
            return ""

        if self.problematic_auth_params != {"OAuth": ParamIssue.MISSING}:
            auth_message = f"the following problems were found among the auth params: {', '.join(str(x) for x in self.problematic_auth_params.items())}"
        else:
            auth_message = (
                "missing starting 'OAuth' from 'Authentication' header"
            )

        get_message = f"the following problems were found among the query params: {', '.join(str(x) for x in self.problematic_get_params.items())}"
        post_message = f"the following problems were found among the query params: {', '.join(str(x) for x in self.problematic_post_params.items())}"

        return "; ".join((auth_message, get_message, post_message))


class MAASAPIAuthentication(OAuthAuthentication):
    """Use the currently logged-in user; resort to OAuth if there isn't one.

    There may be a user already logged-in via another mechanism, like a
    familiar in-browser user/pass challenge.
    """

    def is_authenticated(self, request):
        user = request.user
        if user.is_authenticated:
            # only authenticate if user is local and external auth is disabled
            # or viceversa
            return bool(
                xor(
                    bool(request.external_auth_info), user.userprofile.is_local
                )
            )

        # The following is much the same as is_authenticated from Piston's
        # OAuthAuthentication, with the difference that an OAuth request that
        # does not validate is rejected instead of being silently downgraded.
        validity_report = self.check_validity(request)
        if validity_report.represents_valid_request():
            try:
                consumer, token, _ = self.validate_token(request)
            except OAuthError as error:
                raise OAuthUnauthorized(error)  # noqa: B904
            except OAuthMissingParam as error:
                raise OAuthBadRequest(error)  # noqa: B904

            if consumer and token:
                user = token.user
                if user.username not in SYSTEM_USERS:
                    external_auth_info = request.external_auth_info
                    is_local_user = user.userprofile.is_local
                    if external_auth_info:
                        if is_local_user:
                            return False
                        if not validate_user_external_auth(
                            user, external_auth_info
                        ):
                            return False
                    elif not is_local_user:
                        return False

                request.user = user
                request.consumer = consumer
                request.throttle_extra = token.consumer.id
                return True

            else:
                return False
        # Raising a 400 in case we find type issues.
        # At time of writing, this only happens with oauth_timestamp.
        # Arguably, we should raise this error also with missing params,
        # but this would break previous expectations.
        elif validity_report.contains_invalid_type_issues():
            raise OAuthBadRequest(
                RequestParamsError(validity_report.generate_error_message())
            )
        else:
            # This is here mainly for maintaining previous behavior, which
            # some tests expect. Specifically, ultimately raising 401
            # in case the if check fails.
            #
            # Arguably, both OAuthError in the if block and this should
            # become 400's.
            return False

    def challenge(self, request):
        # Beware: this returns 401: Unauthorized, not 403: Forbidden
        # as the name implies.
        return rc.FORBIDDEN

    @staticmethod
    def check_validity(
        request: WSGIRequest,
    ) -> RequestValidityReport:
        """Generates a RequestValidityReport, containing missing/problematic fields.

        This is basically a stricter check than what is seen in OAuthAuthentications's `is_valid_request`.
        Piston seems to assume things it simply doesn't check for. For example, that `oauth_timestamp` is
        parseable to an int in case it is nonempty.
        """

        auth_params = request.META.get("HTTP_AUTHORIZATION", "")
        get_params = request.GET
        post_params = request.POST

        problematic_auth_params = get_problematic_auth_params(auth_params)
        problematic_get_params = get_problematic_params(get_params)  # type: ignore
        problematic_post_params = get_problematic_params(post_params)

        return RequestValidityReport(
            problematic_auth_params,
            problematic_get_params,
            problematic_post_params,
        )


class RequestParamsError(RuntimeError):
    def __init__(self, message: str):
        self.message = message


def get_problematic_auth_params(params: str) -> dict[str, ParamIssue]:
    """Detects missing auth parameters, or auth parameters with unexpected values.

    Separating this from `get_problematic_params` since the auth params will come
    as a string and we need to do some mild parsing.

    We do not care if there are repeated keys. They will overwrite each other
    in order for the purposes of this check.
    """
    problems: dict[str, ParamIssue] = {}
    params = params.strip()

    if not params.startswith("OAuth"):
        problems = {"OAuth": ParamIssue.MISSING}
        return problems

    params = params.lstrip("OAuth").strip()

    must_have = [
        "oauth_" + s
        for s in [
            "consumer_key",
            "token",
            "signature",
            "signature_method",
            "timestamp",
            "nonce",
        ]
    ]
    split_params = (x.strip() for x in params.split(","))
    keys_and_values = {}
    for param in split_params:
        key, value = param.split("=", 1)
        keys_and_values[key.strip()] = value.strip().strip('"')

    for expected_param in must_have:
        value = keys_and_values.get(expected_param)
        if value is None:
            problems[expected_param] = ParamIssue.MISSING
        elif expected_param == "oauth_timestamp":
            try:
                int(value)
            except ValueError:
                problems[expected_param] = ParamIssue.UNEXPECTED_TYPE

    return problems


def get_problematic_params(params: dict[str, str]) -> dict[str, ParamIssue]:
    """Detects missing parameters, or parameters with unexpected values."""
    must_have = [
        "oauth_" + s
        for s in [
            "consumer_key",
            "token",
            "signature",
            "signature_method",
            "timestamp",
            "nonce",
        ]
    ]
    problems: dict[str, ParamIssue] = {}
    for param in must_have:
        value = params.get(param)
        if value is None:
            problems[param] = ParamIssue.MISSING
        elif param == "oauth_timestamp":
            try:
                int(value)
            except ValueError:
                problems[param] = ParamIssue.UNEXPECTED_TYPE

    return problems


# OAuth and macaroon-based authentication for the APIs.
api_auth = (
    MAASAPIAuthentication(realm="MAAS API"),
    MacaroonAPIAuthentication(),
)
