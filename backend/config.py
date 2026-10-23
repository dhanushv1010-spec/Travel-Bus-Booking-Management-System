import os

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", "1234"),   # <- put your MySQL password here or set DB_PASSWORD
    database=os.getenv("DB_NAME", "busbook"),
)
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-before-deploying")
