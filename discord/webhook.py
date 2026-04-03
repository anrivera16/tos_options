from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv


class DiscordWebhookError(RuntimeError):
    pass


def load_webhook_url() -> str:
    load_dotenv()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url or not webhook_url.strip():
        raise DiscordWebhookError(
            "Missing required Discord configuration: DISCORD_WEBHOOK_URL. "
            "Set it in your environment or .env before running this command."
        )
    return webhook_url.strip()


def validate_png_file(file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.is_file():
        raise DiscordWebhookError(f"Discord upload file was not found: {path}")
    if path.suffix.lower() != ".png":
        raise DiscordWebhookError(f"Discord upload requires a PNG file: {path}")
    return path


def send_png(file_path: str | Path, content: str | None = None) -> None:
    webhook_url = load_webhook_url()
    path = validate_png_file(file_path)

    data = {}
    if content is not None:
        data["content"] = content

    try:
        with path.open("rb") as handle:
            response = requests.post(
                webhook_url,
                data=data,
                files={"file": (path.name, handle, "image/png")},
                timeout=30,
            )
    except requests.RequestException as exc:
        raise DiscordWebhookError(f"Discord webhook request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        if detail:
            raise DiscordWebhookError(
                f"Discord rejected upload with status {response.status_code}: {detail}"
            )
        raise DiscordWebhookError(f"Discord rejected upload with status {response.status_code}.")


def send_message(content: str) -> None:
    webhook_url = load_webhook_url()
    if not content.strip():
        raise DiscordWebhookError("Discord message content cannot be empty.")

    try:
        response = requests.post(webhook_url, json={"content": content}, timeout=30)
    except requests.RequestException as exc:
        raise DiscordWebhookError(f"Discord webhook request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        if detail:
            raise DiscordWebhookError(
                f"Discord rejected message with status {response.status_code}: {detail}"
            )
        raise DiscordWebhookError(f"Discord rejected message with status {response.status_code}.")
