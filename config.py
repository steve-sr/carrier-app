import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")

    DATABASE_URL = os.environ.get("DATABASE_URL")

    if DATABASE_URL:
        # SOLO esto, nada más
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace("mysql://", "mysql+pymysql://")
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///app.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False