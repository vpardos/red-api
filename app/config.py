from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    token_url: str = "https://www.red.cl/planifica-tu-viaje/cuando-llega/"
    prediction_url: str = "https://www.red.cl/predictorPlus/prediccion"
    metro_status_url: str = "https://www.red.cl/mapas-y-horarios/metro/"
    metro_cl_status_url: str = "https://metro.cl/el-viaje/estado-red"
    metrotren_status_url: str = "https://www.red.cl/mapas-y-horarios/metrotren/"
    malla_nocturna_url: str = "https://www.red.cl/mapas-y-horarios/bus/malla-nocturna/"

    token_ttl_seconds: int = 55 * 60
    prediction_cache_ttl_seconds: int = 30
    metro_cache_ttl_seconds: int = 60
    metrotren_cache_ttl_seconds: int = 60
    malla_nocturna_refresh_interval_seconds: int = 12 * 60 * 60  # 6 hours

    request_timeout_seconds: float = 10.0
    docs_enabled: bool = True

    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


settings = Settings()
