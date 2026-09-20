from importlib.resources import files


def read_sql(*parts: str) -> str:
    resource = files("inat.infrastructure.sql").joinpath(*parts)
    return resource.read_text(encoding="utf-8")

