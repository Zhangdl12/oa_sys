from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiResponse(BaseModel):
    """统一接口响应模型。

    用途：
        约束所有业务接口的返回结构，避免不同模块返回格式不一致。
    参数：
        code：业务状态码，0 表示成功。
        msg：业务提示信息。
        data：接口返回的数据内容，可以是对象、数组或空值。
    返回值：
        Pydantic 模型实例，可用于 OpenAPI 文档和响应结构说明。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    code: int
    msg: str
    data: Any = None


def success(data: Any = None, msg: str = "成功") -> dict[str, Any]:
    """构造成功响应。

    用途：
        统一生成成功接口返回值，API 层直接返回该函数结果即可。
    参数：
        data：需要返回给前端的业务数据，默认为空。
        msg：成功提示信息，默认使用“成功”。
    返回值：
        符合统一响应格式的字典。
    """

    return {"code": 0, "msg": msg, "data": data}


def fail(code: int, msg: str, data: Any = None) -> dict[str, Any]:
    """构造失败响应。

    用途：
        统一生成失败接口返回值，主要由异常处理器调用。
    参数：
        code：业务错误码。
        msg：错误提示信息。
        data：可选的错误详情，默认为空。
    返回值：
        符合统一响应格式的字典。
    """

    return {"code": code, "msg": msg, "data": data}
