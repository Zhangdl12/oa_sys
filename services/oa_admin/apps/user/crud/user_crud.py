from typing import Any

USER_SELECT_COLUMNS = """
u.id,
u.username,
u.password_hash,
u.real_name,
u.mobile,
u.email,
u.role_id,
r.role_code,
r.role_name,
u.status,
u.token_version,
u.last_login_at,
u.created_at,
u.updated_at
"""


async def get_user_by_username(mysql_pool: Any, username: str) -> dict[str, Any] | None:
    """按账号查询用户。

    用途：
        登录时根据 username 查询用户基础信息和密码哈希。
    参数：
        mysql_pool：MySQL 异步连接池。
        username：登录账号。
    返回值：
        查询到返回用户字典，否则返回 None。
    """

    sql = f"""
    SELECT {USER_SELECT_COLUMNS}
    FROM sys_user u
    LEFT JOIN sys_role r ON r.id = u.role_id
    WHERE u.username = %s
    LIMIT 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (username,))
            return await cursor.fetchone()


async def get_user_by_id(mysql_pool: Any, user_id: int) -> dict[str, Any] | None:
    """按 ID 查询用户。

    用途：
        login_check 校验 token 后，根据 user_id 查询用户状态和 token_version。
    参数：
        mysql_pool：MySQL 异步连接池。
        user_id：用户 ID。
    返回值：
        查询到返回用户字典，否则返回 None。
    """

    sql = f"""
    SELECT {USER_SELECT_COLUMNS}
    FROM sys_user u
    LEFT JOIN sys_role r ON r.id = u.role_id
    WHERE u.id = %s
    LIMIT 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (user_id,))
            return await cursor.fetchone()


async def list_users(
    mysql_pool: Any,
    keyword: str | None = None,
    status: int | None = None,
    role_id: int | None = None,
) -> list[dict[str, Any]]:
    """查询用户列表。

    用途：
        按可选条件查询 sys_user 用户数据，供用户管理列表接口使用。
    参数：
        mysql_pool：MySQL 异步连接池。
        keyword：登录账号、真实姓名、手机号或邮箱关键字。
        status：用户状态，1 启用，0 禁用。
        role_id：用户所属角色 ID。
    返回值：
        用户字典列表。
    """

    where_parts: list[str] = []
    params: list[Any] = []
    if keyword:
        where_parts.append(
            "(u.username LIKE %s OR u.real_name LIKE %s OR u.mobile LIKE %s OR u.email LIKE %s)"
        )
        keyword_param = f"%{keyword}%"
        params.extend([keyword_param, keyword_param, keyword_param, keyword_param])
    if status is not None:
        where_parts.append("u.status = %s")
        params.append(status)
    if role_id is not None:
        where_parts.append("u.role_id = %s")
        params.append(role_id)

    where_sql = ""
    if where_parts:
        where_sql = "WHERE " + " AND ".join(where_parts)

    sql = f"""
    SELECT {USER_SELECT_COLUMNS}
    FROM sys_user u
    LEFT JOIN sys_role r ON r.id = u.role_id
    {where_sql}
    ORDER BY u.id ASC
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, tuple(params))
            return await cursor.fetchall()


async def insert_user(mysql_pool: Any, payload: dict[str, Any]) -> int:
    """新增用户。

    用途：
        向 sys_user 写入一条用户数据，密码字段只写入 password_hash。
    参数：
        mysql_pool：MySQL 异步连接池。
        payload：已经通过业务层校验的用户字段。
    返回值：
        新增用户 ID。
    """

    sql = """
    INSERT INTO sys_user (
        username,
        password_hash,
        real_name,
        mobile,
        email,
        role_id,
        status
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        payload["username"],
        payload["password_hash"],
        payload["real_name"],
        payload["mobile"],
        payload["email"],
        payload["role_id"],
        payload["status"],
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()
            return int(cursor.lastrowid)


async def update_user(
    mysql_pool: Any,
    user_id: int,
    payload: dict[str, Any],
    increase_token_version: bool,
) -> None:
    """更新用户。

    用途：
        按 ID 更新用户基础资料、角色和状态；必要时自增 token_version。
    参数：
        mysql_pool：MySQL 异步连接池。
        user_id：用户 ID。
        payload：已经通过业务层校验的用户字段。
        increase_token_version：是否自增 token_version，使旧 token 失效。
    返回值：
        无返回值。
    """

    if increase_token_version:
        sql = """
        UPDATE sys_user
        SET real_name = %s,
            mobile = %s,
            email = %s,
            role_id = %s,
            status = %s,
            token_version = token_version + 1
        WHERE id = %s
        """
    else:
        sql = """
        UPDATE sys_user
        SET real_name = %s,
            mobile = %s,
            email = %s,
            role_id = %s,
            status = %s
        WHERE id = %s
        """

    params = (
        payload["real_name"],
        payload["mobile"],
        payload["email"],
        payload["role_id"],
        payload["status"],
        user_id,
    )
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, params)
            await conn.commit()


async def count_enabled_users_by_role_code(mysql_pool: Any, role_code: str) -> int:
    """统计指定启用角色下的启用用户数量。

    用途：
        删除用户前判断是否会删掉最后一个启用的超级管理员。
    参数：
        mysql_pool：MySQL 异步连接池。
        role_code：角色编码。
    返回值：
        启用用户数量。
    """

    sql = """
    SELECT COUNT(*) AS total
    FROM sys_user u
    INNER JOIN sys_role r ON r.id = u.role_id
    WHERE r.role_code = %s
      AND r.status = 1
      AND u.status = 1
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (role_code,))
            row = await cursor.fetchone()
            return int(row["total"] if row else 0)


async def delete_user(mysql_pool: Any, user_id: int) -> None:
    """删除用户。

    用途：
        从 sys_user 中真实删除用户。
    参数：
        mysql_pool：MySQL 异步连接池。
        user_id：用户 ID。
    返回值：
        无返回值。
    """

    sql = """
    DELETE FROM sys_user
    WHERE id = %s
    """
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, (user_id,))
            await conn.commit()
