FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- Microsoft ODBC Driver 18 (MSSQL-ə qoşulmaq üçün pyodbc-yə lazımdır) ---
# libgssapi-krb5-2 msodbcsql18-in özünün asılı olduğu bir kitabxanadır —
# --no-install-recommends onu ötürdüyü üçün açıq şəkildə əlavə edilib.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg2 apt-transport-https ca-certificates libgssapi-krb5-2 \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list -o /etc/apt/sources.list.d/mssql-release.list \
    && sed -i 's#deb \[arch=amd64#deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg arch=amd64#' /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc unixodbc-dev \
    && apt-get purge -y curl gnupg2 \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]