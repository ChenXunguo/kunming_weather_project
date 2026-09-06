from config.config import DB_URL
from sqlalchemy import create_engine, text

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    connect_args={"init_command": "SET time_zone = '+08:00';"}
)

with engine.connect() as conn:
    res = conn.execute(text("SELECT NOW();"))
    print("数据库当前时间：", res.scalar_one())
print("数据库连接成功！")
