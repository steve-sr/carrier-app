import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")

    DATABASE_URL = os.environ.get("DATABASE_URL")

    if DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://")

        SQLALCHEMY_DATABASE_URI = DATABASE_URL
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {
                "ssl": {"ssl-mode": "REQUIRED"}
            }
        }
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///app.db"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    SQLALCHEMY_TRACK_MODIFICATIONS = False