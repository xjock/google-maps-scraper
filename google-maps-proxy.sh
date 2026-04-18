cat << 'EOF' > setup_gmaps_proxy.sh
#!/bin/bash

echo "🚀 开始配置 Google Maps 瓦片反向代理..."

# 1. 创建并进入工作目录
WORK_DIR="gmaps-proxy"
mkdir -p ${WORK_DIR}
cd ${WORK_DIR}

echo "📝 正在生成 Nginx 配置文件 (default.conf)..."
cat << 'INNER_EOF' > default.conf
proxy_cache_path /var/cache/nginx/gmaps_cache levels=1:2 keys_zone=gmaps_cache:50m max_size=10g inactive=30d use_temp_path=off;

server {
    listen 80;
    server_name _;

    location /vt/ {
        proxy_pass https://mt0.google.com/vt/;
        proxy_set_header Host mt0.google.com;
        
        proxy_ssl_server_name on;
        proxy_ssl_protocols TLSv1.2 TLSv1.3;

        proxy_ignore_headers Cache-Control Expires Set-Cookie;
        
        proxy_cache gmaps_cache;
        proxy_cache_valid 200 30d;
        proxy_cache_valid 404 1m;
        
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        
        add_header X-Cache-Status $upstream_cache_status;
        add_header Access-Control-Allow-Origin *;
    }
}
INNER_EOF

echo "📝 正在生成 Dockerfile..."
cat << 'INNER_EOF' > Dockerfile
FROM nginx:alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY default.conf /etc/nginx/conf.d/

RUN mkdir -p /var/cache/nginx/gmaps_cache && \
    chown -R nginx:nginx /var/cache/nginx/gmaps_cache

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
INNER_EOF

echo "📝 正在生成 docker-compose.yml..."
cat << 'INNER_EOF' > docker-compose.yml
version: '3.8'

services:
  gmaps-proxy:
    build: .
    container_name: gmaps-tile-proxy
    ports:
      - "8082:80"
    volumes:
      - gmaps_cache_data:/var/cache/nginx/gmaps_cache
    restart: unless-stopped

volumes:
  gmaps_cache_data:
INNER_EOF

echo "🐳 正在构建并启动 Docker 容器..."
# 兼容老版本 docker-compose 和新版本 docker compose
if command -v docker-compose &> /dev/null; then
    docker-compose up -d --build
elif docker compose version &> /dev/null; then
    docker compose up -d --build
else
    echo "❌ 错误: 未检测到 docker-compose。请先安装 Docker 和 Docker Compose。"
    exit 1
fi

echo ""
echo "✅ 部署完成！"
echo "📍 代理服务已运行在: http://localhost:8080"
echo "👉 在前端代码中使用此链接测试: http://localhost:8080/vt/lyrs=m&x=0&y=0&z=0"
EOF

# 赋予执行权限并立即运行
chmod +x setup_gmaps_proxy.sh
./setup_gmaps_proxy.sh
