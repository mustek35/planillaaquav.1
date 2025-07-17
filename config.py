import os

DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT')
DB_NAME = os.environ.get('DB_NAME')
DB_USER = os.environ.get('DB_USER')
DB_PASS = os.environ.get('DB_PASS')

SFTP_HOST = os.environ.get('SFTP_HOST')
SFTP_PORT = int(os.environ.get('SFTP_PORT', '22')) if os.environ.get('SFTP_PORT') else None
SFTP_USER = os.environ.get('SFTP_USER')
SFTP_PASS = os.environ.get('SFTP_PASS')

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    if all([DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME])
    else None
)
