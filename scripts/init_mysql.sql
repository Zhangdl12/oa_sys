-- 企业 OA 初始化表结构。

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS sys_role (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '角色ID',
    role_code VARCHAR(64) NOT NULL COMMENT '角色编码',
    role_name VARCHAR(100) NOT NULL COMMENT '角色名称',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0禁用',
    remark VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_sys_role_role_code (role_code),
    KEY idx_sys_role_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统角色表';

CREATE TABLE IF NOT EXISTS sys_permission (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '权限ID',
    perm_code VARCHAR(100) NOT NULL COMMENT '权限编码',
    perm_name VARCHAR(100) NOT NULL COMMENT '权限名称',
    perm_type VARCHAR(20) NOT NULL COMMENT '权限类型：menu/button/api',
    parent_id BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '父级权限ID，0表示顶级',
    path VARCHAR(255) NOT NULL DEFAULT '' COMMENT '接口路径或前端菜单路径',
    method VARCHAR(20) NOT NULL DEFAULT '' COMMENT 'HTTP方法',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0禁用',
    sort INT NOT NULL DEFAULT 0 COMMENT '排序值',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_sys_permission_perm_code (perm_code),
    KEY idx_sys_permission_parent_id (parent_id),
    KEY idx_sys_permission_status (status),
    KEY idx_sys_permission_path_method (path, method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统权限表';

CREATE TABLE IF NOT EXISTS sys_user (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    username VARCHAR(64) NOT NULL COMMENT '登录账号',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    real_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '真实姓名',
    mobile VARCHAR(30) NOT NULL DEFAULT '' COMMENT '手机号',
    email VARCHAR(120) NOT NULL DEFAULT '' COMMENT '邮箱',
    role_id BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0禁用',
    token_version INT NOT NULL DEFAULT 1 COMMENT 'Token版本，用于强制旧Token失效',
    last_login_at DATETIME NULL COMMENT '最后登录时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_sys_user_username (username),
    KEY idx_sys_user_role_id (role_id),
    KEY idx_sys_user_status (status),
    CONSTRAINT fk_sys_user_role_id FOREIGN KEY (role_id) REFERENCES sys_role (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统用户表';

CREATE TABLE IF NOT EXISTS sys_role_permission (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '角色权限关联ID',
    role_id BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
    permission_id BIGINT UNSIGNED NOT NULL COMMENT '权限ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_sys_role_permission_role_perm (role_id, permission_id),
    KEY idx_sys_role_permission_role_id (role_id),
    KEY idx_sys_role_permission_permission_id (permission_id),
    CONSTRAINT fk_sys_role_permission_role_id FOREIGN KEY (role_id) REFERENCES sys_role (id),
    CONSTRAINT fk_sys_role_permission_permission_id FOREIGN KEY (permission_id) REFERENCES sys_permission (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色权限关联表';

CREATE TABLE IF NOT EXISTS sys_operation_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '操作日志ID',
    user_id BIGINT UNSIGNED NULL COMMENT '操作用户ID',
    request_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '请求链路ID',
    action VARCHAR(100) NOT NULL DEFAULT '' COMMENT '操作动作',
    path VARCHAR(255) NOT NULL DEFAULT '' COMMENT '请求路径',
    method VARCHAR(20) NOT NULL DEFAULT '' COMMENT 'HTTP方法',
    ip VARCHAR(64) NOT NULL DEFAULT '' COMMENT '客户端IP',
    result VARCHAR(30) NOT NULL DEFAULT '' COMMENT '操作结果',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_sys_operation_log_user_id (user_id),
    KEY idx_sys_operation_log_request_id (request_id),
    KEY idx_sys_operation_log_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统操作日志表';

CREATE TABLE IF NOT EXISTS sys_external_notify_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '外部通知记录ID',
    platform VARCHAR(30) NOT NULL DEFAULT '' COMMENT '外部平台',
    notify_type VARCHAR(30) NOT NULL DEFAULT '' COMMENT '通知类型',
    receive_id_type VARCHAR(30) NOT NULL DEFAULT '' COMMENT '接收ID类型',
    receive_id VARCHAR(255) NOT NULL DEFAULT '' COMMENT '接收ID',
    content_summary VARCHAR(255) NOT NULL DEFAULT '' COMMENT '通知内容摘要',
    sender_user_id BIGINT UNSIGNED NULL COMMENT '发送用户ID',
    request_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '请求链路ID',
    result VARCHAR(30) NOT NULL DEFAULT '' COMMENT '发送结果',
    external_message_id VARCHAR(128) NOT NULL DEFAULT '' COMMENT '外部消息ID',
    error_msg VARCHAR(500) NOT NULL DEFAULT '' COMMENT '失败原因',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_sys_external_notify_log_platform (platform),
    KEY idx_sys_external_notify_log_receive_id (receive_id),
    KEY idx_sys_external_notify_log_result (result),
    KEY idx_sys_external_notify_log_request_id (request_id),
    KEY idx_sys_external_notify_log_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='外部通知发送记录表';

INSERT INTO sys_role (id, role_code, role_name, status, remark)
VALUES
    (1, 'super_admin', '超级管理员', 1, '系统内置最高权限角色'),
    (2, 'staff', '普通员工', 1, '系统内置普通员工角色')
ON DUPLICATE KEY UPDATE
    role_name = VALUES(role_name),
    status = VALUES(status),
    remark = VALUES(remark);

INSERT INTO sys_permission (id, perm_code, perm_name, perm_type, parent_id, path, method, status, sort)
VALUES
    (1, 'system:manage', '系统管理', 'menu', 0, '/system', '', 1, 10),
    (1001, 'user:list', '查询用户列表', 'api', 1, '/v1/users', 'GET', 1, 1001),
    (1002, 'user:create', '创建用户', 'api', 1, '/v1/users', 'POST', 1, 1002),
    (1003, 'user:update', '更新用户', 'api', 1, '/v1/users/{user_id}', 'PUT', 1, 1003),
    (1004, 'user:delete', '删除用户', 'api', 1, '/v1/users/{user_id}', 'DELETE', 1, 1004),
    (2001, 'role:list', '查询角色列表', 'api', 1, '/v1/roles', 'GET', 1, 2001),
    (2002, 'role:create', '创建角色', 'api', 1, '/v1/roles', 'POST', 1, 2002),
    (2003, 'role:update', '更新角色', 'api', 1, '/v1/roles/{role_id}', 'PUT', 1, 2003),
    (2004, 'role:assign_permission', '分配角色权限', 'api', 1, '/v1/roles/{role_id}/permissions', 'PUT', 1, 2004),
    (3001, 'permission:list', '查询权限列表', 'api', 1, '/v1/permissions', 'GET', 1, 3001),
    (3002, 'permission:create', '创建权限', 'api', 1, '/v1/permissions', 'POST', 1, 3002),
    (3003, 'permission:update', '更新权限', 'api', 1, '/v1/permissions/{permission_id}', 'PUT', 1, 3003),
    (4001, 'operation_log:list', '查询操作日志', 'api', 1, '/v1/operation-logs', 'GET', 1, 4001),
    (5001, 'external:feishu_notify', '发送飞书文本通知', 'api', 1, '/v1/external/feishu/notify', 'POST', 1, 5001)
ON DUPLICATE KEY UPDATE
    perm_name = VALUES(perm_name),
    perm_type = VALUES(perm_type),
    parent_id = VALUES(parent_id),
    path = VALUES(path),
    method = VALUES(method),
    status = VALUES(status),
    sort = VALUES(sort);

INSERT INTO sys_permission (id, perm_code, perm_name, perm_type, parent_id, path, method, status, sort)
VALUES
    (5002, 'external:notify_log_list', '查询外部通知记录', 'api', 1, '/v1/external/notify-logs', 'GET', 1, 5002)
ON DUPLICATE KEY UPDATE
    perm_name = VALUES(perm_name),
    perm_type = VALUES(perm_type),
    parent_id = VALUES(parent_id),
    path = VALUES(path),
    method = VALUES(method),
    status = VALUES(status),
    sort = VALUES(sort);

INSERT INTO sys_role_permission (role_id, permission_id)
SELECT 1, p.id
FROM sys_permission p
ON DUPLICATE KEY UPDATE role_id = VALUES(role_id);

SET FOREIGN_KEY_CHECKS = 1;
