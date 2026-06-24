## 服务入口

FastAPI 应用入口：

```text
services.oa_admin.main:app
```

默认接口前缀：

```text
/v1
```

## 接口清单

### 健康检查

```text
GET /v1/health
```

### 登录认证

```text
POST /v1/auth/login
POST /v1/auth/logout
GET  /v1/auth/me
```

### 权限点管理

```text
GET  /v1/permissions
POST /v1/permissions
PUT  /v1/permissions/{permission_id}
```

### 角色管理

```text
GET  /v1/roles
POST /v1/roles
PUT  /v1/roles/{role_id}
PUT  /v1/roles/{role_id}/permissions
```

### 用户管理

```text
GET    /v1/users
GET    /v1/users/{user_id}
POST   /v1/users
PUT    /v1/users/{user_id}
DELETE /v1/users/{user_id}
```

### 操作日志

```text
GET /v1/operation-logs
GET /v1/operation-logs/{log_id}
```

### 飞书与外部通知

```text
POST /v1/external/feishu/notify
POST /v1/external/notify/send-text
POST /v1/external/notify/send-card
GET  /v1/external/notify-logs
```
