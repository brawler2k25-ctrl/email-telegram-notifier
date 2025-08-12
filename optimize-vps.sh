#!/bin/bash

# Скрипт оптимизации VPS для Email Notifier
echo "=== Оптимизация VPS для Email Notifier ==="

# 1. Обновление системы
echo "Обновление системы..."
apt-get update && apt-get upgrade -y

# 2. Установка Docker (минимальная версия)
echo "Установка Docker..."
curl -fsSL https://get.docker.com | sh

# 3. Настройка swap (важно для 1GB RAM!)
echo "Настройка swap файла..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab
    echo "Swap 2GB создан"
else
    echo "Swap уже существует"
fi

# 4. Оптимизация Docker
echo "Оптимизация Docker..."
cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "live-restore": true,
  "userland-proxy": false
}
EOF

systemctl restart docker

# 5. Настройка лимитов системы
echo "Настройка системных лимитов..."
cat >> /etc/sysctl.conf <<EOF

# Оптимизация для Email Notifier
vm.swappiness=60
vm.vfs_cache_pressure=50
net.core.somaxconn=1024
net.ipv4.tcp_max_syn_backlog=1024
EOF

sysctl -p

# 6. Установка docker-compose
echo "Установка docker-compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 7. Создание директории проекта
echo "Создание директории проекта..."
mkdir -p /opt/email-notifier
cd /opt/email-notifier

echo "=== Оптимизация завершена ==="
echo ""
echo "Рекомендации:"
echo "1. Используйте docker-compose-lite.yml вместо docker-compose.yml"
echo "2. В .env установите CHECK_INTERVAL=120 для экономии ресурсов"
echo "3. Разделите 20 почт на группы по приоритету"
echo ""
echo "Память: $(free -h | grep Mem | awk '{print $3"/"$2}')"
echo "Swap: $(free -h | grep Swap | awk '{print $3"/"$2}')"