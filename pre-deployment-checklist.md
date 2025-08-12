# 📋 Подготовка к деплою (пока ждем сервер)

## ✅ Что сделать ПРЯМО СЕЙЧАС:

### 1. 🔐 Безопасность Telegram бота
- [ ] Отозвать старые токены через @BotFather (`/revoke`)
- [ ] Получить новый токен и сохранить в надежном месте
- [ ] НЕ публиковать токен нигде!

### 2. 📧 Подготовка списка почт
Создайте список всех 20 почт в формате:
```
Отдел | Email | Пароль
Sales | sales@domain.com | password123
Support | support@domain.com | password456
...
```

### 3. 🏗️ Создание Telegram групп
- [ ] Создать основную группу для всех уведомлений
- [ ] Создать группы по отделам (опционально):
  - "Продажи - Email"
  - "Поддержка - Email" 
  - "Руководство - Email"
- [ ] Добавить бота во ВСЕ группы как администратора

### 4. 📱 Тестирование бота локально
- [ ] Проверить, что бот отвечает на команды
- [ ] Команда `/start` должна работать в группах

### 5. 🗂️ Организация отделов
Решить какие почты к каким отделам относятся для фильтрации

## 🚀 Готовые файлы для копирования на сервер:

### accounts.yaml (заполните своими данными):
```yaml
accounts:
  - label: "Sales Manager"
    email: "sales@yourdomain.com" 
    password: "ваш_пароль"
    imap_server: "imap.privateemail.com"
    imap_port: 993
    use_ssl: true
    use_idle: false
    
  - label: "Support Team"
    email: "support@yourdomain.com"
    password: "ваш_пароль"
    imap_server: "imap.privateemail.com"
    imap_port: 993
    use_ssl: true
    use_idle: false

  # Добавьте остальные 18 почт...
```

### .env файл (НЕ заполняйте токен здесь!):
```env
TELEGRAM_BOT_TOKEN=сюда_вставить_новый_токен_на_сервере
DATABASE_PATH=data/emails.db
CHECK_INTERVAL=120
LOG_LEVEL=INFO
```

### docker-compose.yml для 2GB сервера:
```yaml
version: '3.8'

services:
  email-notifier:
    build: .
    container_name: email-telegram-notifier
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./accounts.yaml:/app/accounts.yaml:ro
    deploy:
      resources:
        limits:
          cpus: '1.5'
          memory: 1536M
        reservations:
          cpus: '0.5'
          memory: 768M
    logging:
      driver: "json-file"
      options:
        max-size: "20m"
        max-file: "5"
```

## 📝 План установки на сервер (когда получите):

### Шаг 1: Подключение
```bash
ssh root@your_server_ip
```

### Шаг 2: Быстрая установка окружения
```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Docker одной командой
curl -fsSL https://get.docker.com | sh

# Установка git и docker-compose
apt install -y git docker-compose

# Создание рабочей директории
mkdir -p /opt/email-notifier
cd /opt/email-notifier
```

### Шаг 3: Загрузка проекта
```bash
# Клонирование репозитория
git clone <ваш-репозиторий> .

# ИЛИ загрузка файлов вручную через scp/sftp
```

### Шаг 4: Конфигурация
```bash
# Создание .env файла с токеном
nano .env

# Настройка почт
nano accounts.yaml

# Проверка конфигурации
cat .env
cat accounts.yaml
```

### Шаг 5: Запуск
```bash
# Сборка и запуск
docker-compose -f docker-compose-2gb.yml up -d

# Проверка логов
docker-compose logs -f
```

### Шаг 6: Тестирование
```bash
# В Telegram группах отправить:
/subscribe
/status
```

## 🔧 Инструменты для подготовки:

### 1. Текстовый редактор для создания accounts.yaml
### 2. Менеджер паролей для безопасного хранения токена
### 3. SSH клиент (PuTTY для Windows, Terminal для Mac/Linux)
### 4. SCP/SFTP клиент для загрузки файлов на сервер

## ⏱️ Время выполнения:
- Подготовка файлов: 15 минут
- Установка на сервер: 10 минут
- Настройка и тестирование: 15 минут
- **Итого: 40 минут от получения сервера до работающей системы**

## 📞 Поддержка:
Когда получите сервер - просто следуйте плану установки пошагово!