
import os
from pathlib import Path

import oracledb
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Initialize Oracle Client in Thick mode.
oracledb.init_oracle_client(
    lib_dir=r"D:\Sem 3\DBMS\instantclient_23_26"
)


def get_connection():
    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASSWORD")
    host = os.getenv("ORACLE_HOST")
    port = int(os.getenv("ORACLE_PORT", "1521"))
    service = os.getenv("ORACLE_SERVICE")

    if not user or not password:
        raise ValueError("Oracle credentials are missing in .env")

    return oracledb.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        service_name=service,
    )
