from eth_typing import (
    URI,
)
from eth_utils import (
    to_dict,
)
import logging
import random
from requests import (
    RequestException,
)
from datetime import datetime
from typing import (
    Any,
    Dict,
    Iterable,
    Optional,
    Tuple,
    Union,
)

from web3._utils.http import (
    construct_user_agent,
)
from web3._utils.request import (
    cache_session,
    get_default_http_endpoint,
    make_post_request,
)
from web3.datastructures import (
    NamedElementOnion,
)
from web3.exceptions import (
    CannotHandleRequest,
)
from web3.middleware import (
    http_retry_request_middleware,
)
from web3.providers import (
    BaseProvider,
)
from web3.types import (
    Middleware,
    RPCEndpoint,
    RPCResponse,
)

from .base import (
    JSONBaseProvider,
)


class HTTPProvider(JSONBaseProvider):
    logger = logging.getLogger("web3.providers.HTTPProvider")
    providers = None
    randomize = False
    _request_args = None
    _request_kwargs = None
    # type ignored b/c conflict with _middlewares attr on BaseProvider
    _middlewares: Tuple[Middleware, ...] = NamedElementOnion([(http_retry_request_middleware, "http_retry_request")])  # type: ignore # noqa: E501

    def __init__(
        self,
        providers: Union[list, str],
        randomize: Optional[bool] = False,
        request_kwargs: Optional[Any] = None,
        session: Optional[Any] = None,
        block_timeout_sec: Optional[int] = None,
    ) -> None:
        if isinstance(providers, str):
            providers = [
                providers,
            ]
        self.randomize = randomize
        self.providers = providers
        self._request_kwargs = request_kwargs or {}
        self.block_timeout_sec = block_timeout_sec

        if session:
            cache_session(self.providers[0], session)

        super().__init__()

    def __str__(self) -> str:
        return "RPC connection {0}".format(self.providers)

    @to_dict
    def get_request_kwargs(self) -> Iterable[Tuple[str, Any]]:
        if "headers" not in self._request_kwargs:
            yield "headers", self.get_request_headers()
        for key, value in self._request_kwargs.items():
            yield key, value

    def get_request_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": construct_user_agent(str(type(self))),
        }

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        request_data = self.encode_rpc_request(method, params)
        if self.randomize:
            random.shuffle(self.providers)
        for provider in self.providers:
            provider_uri = URI(provider)
            self.logger.debug(
                "Making request HTTP. URI: %s, Method: %s", provider_uri, method
            )
            try:
                if self.block_timeout_sec:
                    request_data_for_block = self.encode_rpc_request(
                        "eth_getBlockByNumber", ("latest", False)
                    )
                    raw_response = make_post_request(
                        provider_uri,
                        request_data_for_block,
                        **self.get_request_kwargs()
                    )
                    response = self.decode_rpc_response(raw_response)
                    last_block_timestamp = int(
                        response.get("result").get("timestamp"), base=16
                    )
                    now_timestamp = datetime.now().timestamp()
                    if now_timestamp - last_block_timestamp > self.block_timeout_sec:
                        continue

                raw_response = make_post_request(
                    provider_uri, request_data, **self.get_request_kwargs()
                )
                response = self.decode_rpc_response(raw_response)
                self.logger.debug(
                    "Getting response HTTP. URI: %s, " "Method: %s, Response: %s",
                    provider_uri,
                    method,
                    response,
                )
                return response
            except RequestException:
                pass
        else:
            raise CannotHandleRequest
