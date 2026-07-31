from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    token_url: str = "https://www.red.cl/planifica-tu-viaje/cuando-llega/"
    prediction_url: str = "https://www.red.cl/predictorPlus/prediccion"
    metro_status_url: str = "https://www.red.cl/mapas-y-horarios/metro/"
    metro_cl_status_url: str = "https://metro.cl/el-viaje/estado-red"
    metrotren_status_url: str = "https://www.red.cl/mapas-y-horarios/metrotren/"

    token_ttl_seconds: int = 55 * 60
    prediction_cache_ttl_seconds: int = 30
    metro_cache_ttl_seconds: int = 60
    metrotren_cache_ttl_seconds: int = 60

    request_timeout_seconds: float = 10.0

    # When False, disables the interactive documentation endpoints
    # (/docs, /redoc) and the OpenAPI schema (/openapi.json).
    # Recommended for public deployments to avoid exposing the full API surface.
    # Override at deploy time, e.g.:
    #     from app.config import Settings; settings = Settings(docs_enabled=False)
    docs_enabled: bool = True

    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


settings = Settings()
