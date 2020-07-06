##
# Dolibarr docker image
#
# Jakob Gurnhofer <jakob@gurn.at>
#

FROM    php:apache
LABEL   maintainer="Jakob Gurnhofer <jakob@gurn.at>" \
        version="1.0" \
        description="Dolibarr on php-apache with auto installation"

ENV DOLI_INSTALL_AUTO=1 \
    DOLI_PROD=1 \
    DOLI_DB_TYPE=mysql \
    DOLI_DB_HOST=dbhost \
    DOLI_DB_PORT=3306 \
    DOLI_DB_USER=doli \
    DOLI_DB_PASSWORD=doli_pass \
    DOLI_DB_NAME=dolidb \
    DOLI_ADMIN_LOGIN=admin \
    DOLI_ADMIN_PASSWORD=admin \
    DOLI_URL_ROOT='http://localhost' \
    WWW_USER_ID=33 \
    WWW_GROUP_ID=33 \
    PHP_INI_DATE_TIMEZONE='UTC'

RUN mkdir -p /usr/share/man/man1 && \
    apt update && \
    DEBIAN_FRONTEND=noninteractive apt install -y \
        default-jre-headless \
        fonts-liberation2 \
        libicu-dev \
        libpng-dev \
        libxml2-dev \
        libzip-dev \
        libreoffice-core \
        libreoffice-java-common \
        mariadb-client \
        python3-mysqldb && \
    docker-php-ext-install gd intl mysqli pdo pdo_mysql soap zip

RUN echo "Adding SourceSansPro fonts" && \
    mkdir -p /usr/share/fonts/source-sans-pro && \
    for TYPE in Black BlackIt Bold BoldIt ExtraLight ExtraLightIt It Light LightIt Regular Semibold SemiboldIt; do \
        curl -o /usr/share/fonts/source-sans-pro/SourceSansPro-${TYPE}.ttf https://raw.githubusercontent.com/adobe-fonts/source-sans-pro/release/TTF/SourceSansPro-${TYPE}.ttf; \
    done

ENV DOLI_VERSION=11.0.5
# Get Dolibarr
ADD https://github.com/Dolibarr/dolibarr/archive/${DOLI_VERSION}.zip /tmp/dolibarr.zip

EXPOSE    80
VOLUME    ["/var/www/documents", "/var/www/html", "/var/www/scripts"]
COPY    doli-run.py /usr/local/bin/doli-run.py
CMD    ["/usr/local/bin/doli-run.py"]
