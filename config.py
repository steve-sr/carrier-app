import os
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    DATABASE_URL = os.environ.get("DATABASE_URL")

    if DATABASE_URL:
        db_url = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

        # Limpia parámetros que PyMySQL no entiende bien desde Aiven
        parsed = urlsplit(db_url)
        query = dict(parse_qsl(parsed.query))
        query.pop("ssl-mode", None)
        query.pop("ssl", None)

        cleaned_query = urlencode(query)
        SQLALCHEMY_DATABASE_URI = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.query and cleaned_query,
                parsed.fragment,
            )
        )

        # Aiven normalmente requiere SSL. PyMySQL espera un dict.
        if "aivencloud.com" in SQLALCHEMY_DATABASE_URI:
            SQLALCHEMY_ENGINE_OPTIONS = {
                "connect_args": {
                    "ssl": {}
                }
            }
        else:
            SQLALCHEMY_ENGINE_OPTIONS = {}
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///app.db"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    SQLALCHEMY_TRACK_MODIFICATIONS = False