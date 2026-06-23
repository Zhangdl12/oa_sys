from typing import Any

PERMISSION_SELECT_COLUMNS = """
id,
perm_code,
perm_name,
perm_type,
parent_id,
path,
method,
status,
sort,
created_at,
updated_at
"""


async def list_permissions(
    mysql_pool: Any,
    keyword: str | None = None,
    perm_type: str | None = None,
    status: int | None = None,
    parent_id: int | None = None,
) -> list[dict[str, Any]]:
    """查询权限点列表。

    用途：
        按可选条件查询 sys_permission 权限点，供权限管理列表接口使用。
    参数：
        mysql_pool：MySQL 异步连接池。
        keyword：权限编码或权限名称关键字。
        perm_type：权限类型，可选 menu、button、api。
        status：权限状态，1 启用，0 禁用。
        parent_id：父级权限 ID。
    返回值：
        权限点字典列表。
    """

    where_parts: list[str] = []
    params: list[Any] = []
    if keyword:
        where_parts.append("(perm_code LIKE %s OR perm_name LIKE %s)")
        keyword_param = f"%{keyword}%"
        params.extend([keyword_param, keyword_param])
    if perm_type:
        where_parts.append("perm_type = %s")
        params.append(perm_type)
    if status is not None:
        where_parts.append("status = %s")
        params.append(status)
    if parent_id is not None:
        where_parts.append("parent_id = %s")
        params.append(parent_id)

    where_sql = ""
    if where_parts:
        where_sql = "WHERE " + " AND ".join(where_parts)

    sql = f"""
    SELECT {PERMISSION_SELECT_COLUMNS}
    FROM sys_permission
    {where_sql}
    ORDER BY sort ASC, id ASC
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(params))
            return await cursor.fetchall()


async def get_permission_by_id(mysql_pool: Any, permission_id: int) -> dict[str, Any] | None:
    """按 ID 查询权限点。

    用途：
        为权限更新、父级权限校验和创建后回读提供单条权限点查询。
    参数：
        mysql_pool：MySQL 异步连接池。
        permission_id：权限点 ID。
    返回值：
        查询到返回权限点字典，否则返回 None。
    """

    sql = f"""
    SELECT {PERMISSION_SELECT_COLUMNS}
    FROM sys_permission
    WHERE id = %s
    LIMIT 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (permission_id,))
            return await cursor.fetchone()


async def get_permission_by_code(mysql_pool: Any, perm_code: str) -> dict[str, Any] | None:
    """按权限编码查询权限点。

    用途：
        创建权限点前校验 perm_code 是否已经存在。
    参数：
        mysql_pool：MySQL 异步连接池。
        perm_code：权限编码。
    返回值：
        查询到返回权限点字典，否则返回 None。
    """

    sql = f"""
    SELECT {PERMISSION_SELECT_COLUMNS}
    FROM sys_permission
    WHERE perm_code = %s
    LIMIT 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (perm_code,))
            return await cursor.fetchone()


async def insert_permission(mysql_pool: Any, payload: dict[str, Any]) -> int:
    """新增权限点。

    用途：
        向 sys_permission 写入一条权限点数据。
    参数：
        mysql_pool：MySQL 异步连接池。
        payload：已经通过业务层校验的权限点字段。
    返回值：
        新增权限点 ID。
    """

    sql = """
    INSERT INTO sys_permission (
        perm_code,
        perm_name,
        perm_type,
        parent_id,
        path,
        method,
        status,
        sort
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        payload["perm_code"],
        payload["perm_name"],
        payload["perm_type"],
        payload["parent_id"],
        payload["path"],
        payload["method"],
        payload["status"],
        payload["sort"],
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()
            return int(cursor.lastrowid) # lastrowid是新增的行ID


async def update_permission(
    mysql_pool: Any,
    permission_id: int,
    payload: dict[str, Any],
) -> None:
    """更新权限点。

    用途：
        按 ID 更新权限点可变字段，不允许修改 perm_code。
    参数：
        mysql_pool：MySQL 异步连接池。
        permission_id：权限点 ID。
        payload：已经通过业务层校验的权限点字段。
    返回值：
        无返回值。
    """

    sql = """
    UPDATE sys_permission
    SET perm_name = %s,
        perm_type = %s,
        parent_id = %s,
        path = %s,
        method = %s,
        status = %s,
        sort = %s
    WHERE id = %s
    """
    params = (
        payload["perm_name"],
        payload["perm_type"],
        payload["parent_id"],
        payload["path"],
        payload["method"],
        payload["status"],
        payload["sort"],
        permission_id,
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()


async def list_permission_codes_by_role_id(mysql_pool: Any, role_id: int) -> list[str]:
    """按角色 ID 查询权限编码列表。

    用途：
        为 RBAC 权限校验提供当前角色拥有的启用权限编码。
    参数：
        mysql_pool：MySQL 异步连接池。
        role_id：当前用户所属角色 ID。
    返回值：
        权限编码字符串列表；角色禁用、权限禁用或无权限时返回空列表。
    """

    sql = """
    SELECT p.perm_code
    FROM sys_role r
    INNER JOIN sys_role_permission rp ON rp.role_id = r.id
    INNER JOIN sys_permission p ON p.id = rp.permission_id
    WHERE r.id = %s
      AND r.status = 1
      AND p.status = 1
    ORDER BY p.sort ASC, p.id ASC
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (role_id,))
            rows = await cursor.fetchall()
            return [str(row["perm_code"]) for row in rows]
