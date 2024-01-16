import logging
import os

import fastapi
import gradio
from fastapi.responses import RedirectResponse
from gradio.oauth import MOCKED_OAUTH_TOKEN

from modules.presets import i18n

OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET")
OAUTH_SCOPES = os.environ.get("OAUTH_SCOPES")
OPENID_PROVIDER_URL = os.environ.get("OPENID_PROVIDER_URL")
def _add_oauth_routes(app: fastapi.FastAPI) -> None:
    """Add OAuth routes to the FastAPI app (login, callback handler and logout)."""
    try:
        from authlib.integrations.starlette_client import OAuth
    except ImportError as e:
        raise ImportError(
            "Cannot initialize OAuth to due a missing library. Please run `pip install gradio[oauth]` or add "
            "`gradio[oauth]` to your requirements.txt file in order to install the required dependencies."
        ) from e

    # Check environment variables
    msg = (
        "OAuth is required but {} environment variable is not set. Make sure you've enabled OAuth in your Space by"
        " setting `hf_oauth: true` in the Space metadata."
    )
    if OAUTH_CLIENT_ID is None:
        raise ValueError(msg.format("OAUTH_CLIENT_ID"))
    if OAUTH_CLIENT_SECRET is None:
        raise ValueError(msg.format("OAUTH_CLIENT_SECRET"))
    if OAUTH_SCOPES is None:
        raise ValueError(msg.format("OAUTH_SCOPES"))
    if OPENID_PROVIDER_URL is None:
        raise ValueError(msg.format("OPENID_PROVIDER_URL"))

    # Register OAuth server
    oauth = OAuth()
    oauth.register(
        name="huggingface",
        client_id=OAUTH_CLIENT_ID,
        client_secret=OAUTH_CLIENT_SECRET,
        client_kwargs={"scope": OAUTH_SCOPES},
        server_metadata_url=OPENID_PROVIDER_URL + "/.well-known/openid-configuration",
    )

    # Define OAuth routes
    @app.get("/login/huggingface")
    async def oauth_login(request: fastapi.Request):
        """Endpoint that redirects to HF OAuth page."""
        redirect_uri = str(request.url_for("oauth_redirect_callback"))
        if ".hf.space" in redirect_uri:
            # In Space, FastAPI redirect as http but we want https
            redirect_uri = redirect_uri.replace("http://", "https://")
        return await oauth.huggingface.authorize_redirect(request, redirect_uri)

    @app.get("/login/callback")
    async def oauth_redirect_callback(request: fastapi.Request) -> RedirectResponse:
        """Endpoint that handles the OAuth callback."""
        token = await oauth.huggingface.authorize_access_token(request)
        request.session["oauth_profile"] = token["userinfo"]
        request.session["oauth_token"] = token
        return RedirectResponse("/")

    @app.get("/logout")
    async def oauth_logout(request: fastapi.Request) -> RedirectResponse:
        """Endpoint that logs out the user (e.g. delete cookie session)."""
        request.session.pop("oauth_profile", None)
        request.session.pop("oauth_token", None)
        # 清除cookie并跳转到首页
        response = RedirectResponse(url="/", status_code=302)
        response.delete_cookie(key=f"access-token")
        response.delete_cookie(key=f"access-token-unsecure")
        return response


def _add_mocked_oauth_routes(app: fastapi.FastAPI) -> None:
    """Add fake oauth routes if Gradio is run locally and OAuth is enabled.

    Clicking on a gr.LoginButton will have the same behavior as in a Space (i.e. gets redirected in a new tab) but
    instead of authenticating with HF, a mocked user profile is added to the session.
    """

    # Define OAuth routes
    @app.get("/login/huggingface")
    async def oauth_login(request: fastapi.Request):
        """Fake endpoint that redirects to HF OAuth page."""
        return RedirectResponse("/login/callback")

    @app.get("/login/callback")
    async def oauth_redirect_callback(request: fastapi.Request) -> RedirectResponse:
        """Endpoint that handles the OAuth callback."""
        request.session["oauth_profile"] = MOCKED_OAUTH_TOKEN["userinfo"]
        request.session["oauth_token"] = MOCKED_OAUTH_TOKEN
        return RedirectResponse("/")

    @app.get("/logout")
    async def oauth_logout(request: fastapi.Request) -> RedirectResponse:
        """Endpoint that logs out the user (e.g. delete cookie session)."""
        request.session.pop("oauth_profile", None)
        request.session.pop("oauth_token", None)
        # 清除cookie并跳转到首页
        response = RedirectResponse(url="/", status_code=302)
        response.delete_cookie(key=f"access-token")
        response.delete_cookie(key=f"access-token-unsecure")
        return response


def reg_patch():
    gradio.oauth._add_mocked_oauth_routes = _add_mocked_oauth_routes
    gradio.oauth._add_oauth_routes = _add_oauth_routes
    logging.info(i18n("覆盖gradio.oauth /logout路由"))
