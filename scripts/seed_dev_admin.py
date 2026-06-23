import asyncio
import os
from dataclasses import dataclass

import asyncmy
from asyncmy.cursors import DictCursor
from common.security import hash_password


@dataclass(frozen=True)
class SeedSettings:
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    admin_username: str
    admin_password: str


def load_settings() -> SeedSettings:
    admin_username = os.getenv("OA_DEV_ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("OA_DEV_ADMIN_PASSWORD", "")
    if not admin_username:
        raise RuntimeError("OA_DEV_ADMIN_USERNAME is required")
    if not admin_password:
        raise RuntimeError("OA_DEV_ADMIN_PASSWORD is required")

    return SeedSettings(
        mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
        mysql_user=os.getenv("MYSQL_USER", "oa_user"),
        mysql_password=os.getenv("MYSQL_PASSWORD", "oa_password"),
        mysql_database=os.getenv("MYSQL_DATABASE", "oa"),
        admin_username=admin_username,
        admin_password=admin_password,
    )


async def seed_admin(settings: SeedSettings) -> None:
    conn = await asyncmy.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_database,
        charset="utf8mb4",
        autocommit=False,
        cursor_cls=DictCursor,
    )
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id
                FROM sys_role
                WHERE role_code = %s
                LIMIT 1
                """,
                ("super_admin",),
            )
            role = await cursor.fetchone()
            if role is None:
                raise RuntimeError("super_admin role not found, run scripts/init_mysql.sql first")

            password_hash = hash_password(settings.admin_password)
            await cursor.execute(
                """
                INSERT INTO sys_user (
                    username,
                    password_hash,
                    real_name,
                    mobile,
                    email,
                    role_id,
                    status
                )
                VALUES (%s, %s, %s, '', '', %s, 1)
                ON DUPLICATE KEY UPDATE
                    password_hash = VALUES(password_hash),
                    real_name = VALUES(real_name),
                    role_id = VALUES(role_id),
                    status = 1,
                    token_version = token_version + 1
                """,
                (
                    settings.admin_username,
                    password_hash,
                    "本地管理员",
                    role["id"],
                ),
            )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        conn.close()


async def main() -> None:
    settings = load_settings()
    await seed_admin(settings)
    print(f"Seeded local admin user: {settings.admin_username}")


if __name__ == "__main__":
    asyncio.run(main())
