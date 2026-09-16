from fastapi import Response


def set_private_version(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'
    response.headers["Cache-Control"] = "private, no-cache"
