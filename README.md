# docker-dolibarr
Docker image for Dolibarr, based on https://github.com/tuxgasy/docker-dolibarr

# How to run
with docker-compose:
```yaml
version: "3.7"

volumes:
  dbdata:
  doliwww:
  dolidocs:
  doliscripts:

services:
  db:
    image: "mariadb"
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
    volumes:
      - "dbdata:/var/lib/mysql"
    environment:
      MYSQL_RANDOM_ROOT_PASSWORD: "yes"
      MYSQL_DATABASE: "dolibarr"
      MYSQL_USER: "dolibarr"
      MYSQL_PASSWORD: "change_me"

  doli:
    image: "jakobgurn/dolibarr:latest"
    depends_on:
      - "db"
    volumes:
      - "doliwww:/var/www/html"
      - "dolidocs:/var/www/documents"
      - "doliscripts:/var/www/scripts"
    ports:
      - "8000:80"
    environment:
      DOLI_INSTALL_AUTO: 1
      DOLI_PROD: 0
      DOLI_DB_TYPE: "mysql"
      DOLI_DB_HOST: "db"
      DOLI_DB_PORT: "3306"
      DOLI_DB_USER: "dolibarr"
      DOLI_DB_PASSWORD: "change_me"
      DOLI_DB_NAME: "dolibarr"
      DOLI_URL_ROOT: "http://localhost:8000"
      PHP_INI_DATE_TIMEZONE: "UTC"
```

# Environment variables

Variable | Default | Description
--- | --- | ---
**DOLI_INSTALL_AUTO** | *1* | run auto-installation on first start
**DOLI_PROD** | *1* | set doli_main_prod to 1 to prevent errors from showing
**DOLI_DB_TYPE** | *mysql* | type of database to use (currently only mysql/mariadb is supported, postgres is planned)
**DOLI_DB_HOST** | *dbhost* | hostname of database server
**DOLI_DB_PORT** | *3306* | port of database 
**DOLI_DB_USER** | *doli* | database user
**DOLI_DB_PASSWORD** | *doli_pass* | database password
**DOLI_DB_NAME** | *dolidb* | database name
**DOLI_ADMIN_LOGIN** | *admin* | admin username
**DOLI_ADMIN_PASSWORD** | *admin* | admin password
**DOLI_URL_ROOT** | *http://localhost* | root of dolibarr installation
**WWW_USER_ID** | *33* | id of www-data user
**WWW_GROUP_ID** | *33* | id of www-data group
**PHP_INI_DATE_TIMEZONE** | *UTC* | PHP timezone
