import os
import base64
import datetime
import json
import webbrowser
from dataclasses import dataclass

import requests
from dotenv import load_dotenv
import schwabdev


class SchwabConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SchwabConfig:
    api_key: str
    api_secret: str
    redirect_uri: str
    timeout: int = 120


def load_config(timeout: int = 120) -> SchwabConfig:
    load_dotenv()

    values = {
        "SCHWAB_API_KEY": os.getenv("SCHWAB_API_KEY"),
        "SCHWAB_API_SECRET": os.getenv("SCHWAB_API_SECRET"),
        "SCHWAB_REDIRECT_URI": os.getenv("SCHWAB_REDIRECT_URI"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        missing_list = ", ".join(missing)
        raise SchwabConfigError(
            f"Missing required Schwab configuration: {missing_list}. "
            "Set them in your environment or .env before running this command."
        )

    api_key = values["SCHWAB_API_KEY"]
    api_secret = values["SCHWAB_API_SECRET"]
    redirect_uri = values["SCHWAB_REDIRECT_URI"]

    assert api_key is not None
    assert api_secret is not None
    assert redirect_uri is not None

    return SchwabConfig(
        api_key=api_key,
        api_secret=api_secret,
        redirect_uri=redirect_uri,
        timeout=timeout,
    )


def create_client(timeout: int = 120) -> schwabdev.Client:
    config = load_config(timeout=timeout)
    return schwabdev.Client(
        config.api_key,
        config.api_secret,
        config.redirect_uri,
        timeout=config.timeout,
    )


def exchange_callback_for_tokens(callback_url: str, token_file: str = "tokens.json") -> None:
    config = load_config()
    code = callback_url[callback_url.index("code=") + 5 : callback_url.index("%40")] + "@"
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"{config.api_key}:{config.api_secret}".encode()).decode(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": config.redirect_uri}
    response = requests.post("https://api.schwabapi.com/v1/oauth/token", headers=headers, data=data)
    if not response.ok:
        raise RuntimeError(f"Token exchange failed ({response.status_code}): {response.text}")
    now = datetime.datetime.now(datetime.timezone.utc)
    with open(token_file, "w") as f:
        json.dump(
            {"access_token_issued": now.isoformat(), "refresh_token_issued": now.isoformat(), "token_dictionary": response.json()},
            f,
            indent=4,
        )


def build_authorize_url() -> str:
    config = load_config()
    return (
        "https://api.schwabapi.com/v1/oauth/authorize"
        f"?client_id={config.api_key}&redirect_uri={config.redirect_uri}"
    )
