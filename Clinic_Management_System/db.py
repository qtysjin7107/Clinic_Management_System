import os
from pathlib import Path

import oracledb
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Configure Thick mode only when a client library directory is explicitly supplied
# or the legacy Windows path exists. Thin mode works for newer Oracle servers.
_client_dir = os.getenv("ORACLE_CLIENT_LIB_DIR")
if not _client_dir:
    _legacy = Path(r"D:\Sem 3\DBMS\instantclient_23_26")
    if _legacy.exists():
        _client_dir = str(_legacy)
if _client_dir and Path(_client_dir).exists():
    try:
        oracledb.init_oracle_client(lib_dir=_client_dir)
    except oracledb.ProgrammingError as exc:
        if "already been initialized" not in str(exc).lower():
            raise

def get_connection():
    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASSWORD")
    host = os.getenv("ORACLE_HOST", "localhost")
    port = int(os.getenv("ORACLE_PORT", "1521"))
    service = os.getenv("ORACLE_SERVICE", "xe")
    if not user or not password:
        raise ValueError("Oracle credentials are missing in .env")
    return oracledb.connect(user=user, password=password, host=host, port=port, service_name=service)
