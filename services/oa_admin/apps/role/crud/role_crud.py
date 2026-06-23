from typing import Any

ROLE_SELECT_COLUMNS = """
id,
role_code,
role_name,
status,
remark,
created_at,
updated_at
"""


async def list_roles(
    mysql_pool: Any,
    keyword: str | None = None,
    status: int | None = None,
) -> list[dict[str, Any]]:
    """查询角色列表。

    用途：
        按可选条件查询 sys_role 角色数据，供角色管理列表接口使用。
    参数：
        mysql_pool：MySQL 异步连接池。
        keyword：角色编码或角色名称关键字。
        status：角色状态，1 启用，0 禁用。
    返回值：
        角色字典列表。
    """

    where_parts: list[str] = []
    params: list[Any] = []
    if keyword:
        where_parts.append("(role_code LIKE %s OR role_name LIKE %s)")
        keyword_param = f"%{keyword}%"
        params.extend([keyword_param, keyword_param])
    if status is not None:
        where_parts.append("status = %s")
        params.append(status)

    where_sql = ""
    if where_parts:
        where_sql = "WHERE " + " AND ".join(where_parts)

    sql = f"""
    SELECT {ROLE_SELECT_COLUMNS}
    FROM sys_role
    {where_sql}
    ORDER BY id ASC
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(params))
            return await cursor.fetchall()


async def get_role_by_id(mysql_pool: Any, role_id: int) -> dict[str, Any] | None:
    """按 ID 查询角色。

    用途：
        为角色更新、分配权限和创建后回读提供单条角色查询。
    参数：
        mysql_pool：MySQL 异步连接池。
        role_id：角色 ID。
    返回值：
        查询到返回角色字典，否则返回 None。
    """

    sql = f"""
    SELECT {ROLE_SELECT_COLUMNS}
    FROM sys_role
    WHERE id = %s
    LIMIT 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (role_id,))
            return await cursor.fetchone()


async def get_role_by_code(mysql_pool: Any, role_code: str) -> dict[str, Any] | None:
    """按角色编码查询角色。

    用途：
        创建角色前校验 role_code 是否已经存在。
    参数：
        mysql_pool：MySQL 异步连接池。
        role_code：角色编码。
    返回值：
        查询到返回角色字典，否则返回 None。
    """

    sql = f"""
    SELECT {ROLE_SELECT_COLUMNS}
    FROM sys_role
    WHERE role_code = %s
    LIMIT 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (role_code,))
            return await cursor.fetchone()


async def insert_role(mysql_pool: Any, payload: dict[str, Any]) -> int:
    """新增角色。

    用途：
        向 sys_role 写入一条角色数据。
    参数：
        mysql_pool：MySQL 异步连接池。
        payload：已经通过业务层校验的角色字段。
    返回值：
        新增角色 ID。
    """

    sql = """
    INSERT INTO sys_role (role_code, role_name, status, remark)
    VALUES (%s, %s, %s, %s)
    """
    params = (
        payload["role_code"],
        payload["role_name"],
        payload["status"],
        payload["remark"],
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()
            return int(cursor.lastrowid)


async def update_role(mysql_pool: Any, role_id: int, payload: dict[str, Any]) -> None:
    """更新角色。

    用途：
        按 ID 更新角色名称、状态和备注，不允许修改 role_code。
    参数：
        mysql_pool：MySQL 异步连接池。
        role_id：角色 ID。
        payload：已经通过业务层校验的角色字段。
    返回值：
        无返回值。
    """

    sql = """
    UPDATE sys_role
    SET role_name = %s,
        status = %s,
        remark = %s
    WHERE id = %s
    """
    params = (
        payload["role_name"],
        payload["status"],
        payload["remark"],
        role_id,
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()


async def list_user_ids_by_role_id(mysql_pool: Any, role_id: int) -> list[int]:
    """查询使用指定角色的用户 ID。

    用途：
        角色更新或分配权限后，定位需要清理 RBAC 缓存的用户。
    参数：
        mysql_pool：MySQL 异步连接池。
        role_id：角色 ID。
    返回值：
        用户 ID 列表。
    """

    sql = """
    SELECT id
    FROM sys_user
    WHERE role_id = %s
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (role_id,))
            rows = await cursor.fetchall()
            return [int(row["id"]) for row in rows]


async def list_enabled_permission_ids_by_ids(
    mysql_pool: Any,
    permission_ids: list[int],
) -> list[int]:
    """按 ID 列表查询启用权限点。

    用途：
        分配角色权限前，校验传入权限 ID 是否全部存在且启用。
    参数：
        mysql_pool：MySQL 异步连接池。
        permission_ids：权限 ID 列表。
    返回值：
        存在且启用的权限 ID 列表。
    """

    if not permission_ids:
        return []

    placeholders = ",".join(["%s"] * len(permission_ids))
    sql = f"""
    SELECT id
    FROM sys_permission
    WHERE id IN ({placeholders})
      AND status = 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(permission_ids))
            rows = await cursor.fetchall()
            return [int(row["id"]) for row in rows]


async def replace_role_permissions(
    mysql_pool: Any,
    role_id: int,
    permission_ids: list[int],
) -> None:
    """替换角色权限关联。

    用途：
        在同一个事务中删除角色旧权限关联，并写入新的权限关联。
    参数：
        mysql_pool：MySQL 异步连接池。
        role_id：角色 ID。
        permission_ids：新的权限 ID 列表。
    返回值：
        无返回值。
    """

    delete_sql = """
    DELETE FROM sys_role_permission
    WHERE role_id = %s
    """
    insert_sql = """
    INSERT INTO sys_role_permission (role_id, permission_id)
    VALUES (%s, %s)
    """
    async with mysql_pool.acquire() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(delete_sql, (role_id,))
                if permission_ids:
                    params = [(role_id, permission_id) for permission_id in permission_ids]
                    await cursor.executemany(insert_sql, params)
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
