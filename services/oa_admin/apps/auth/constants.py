# 单个登录态 key，按用户 ID 和 JWT jti 精确定位一次登录。
LOGIN_TOKEN_KEY_TEMPLATE = "oa:login:{user_id}:{jti}"
# 用户登录态扫描 pattern，用于禁用用户或调整角色后清理全部登录态。
LOGIN_USER_KEY_PATTERN = "oa:login:{user_id}:*"
# 单个用户 RBAC 权限缓存 key，用于接口权限校验。
RBAC_USER_KEY_TEMPLATE = "oa:rbac:user:{user_id}"
# 用户 RBAC 权限缓存扫描 pattern，用于权限点变更后批量清理。
RBAC_USER_KEY_PATTERN = "oa:rbac:user:*"
