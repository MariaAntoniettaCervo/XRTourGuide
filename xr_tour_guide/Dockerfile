FROM python:3.12

WORKDIR /workspace

COPY . .

RUN apt-get update && \
    apt-get install -y default-libmysqlclient-dev build-essential \
    && pip install -r requirements.txt \
    && apt-get install -y gettext \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get install -y ca-certificates \
    && update-ca-certificates

RUN pip install gunicorn

CMD sh -c "\
    python manage.py makemigrations && \
    python manage.py migrate && \
    python manage.py init_groups && \
    python manage.py collectstatic --noinput && \
    # python manage.py makemessages -l it && \
    # python translate_po.py --full && \
    python manage.py compilemessages && \
    gunicorn --bind 0.0.0.0:8001 --timeout 900 --graceful-timeout 30 xr_tour_guide.wsgi:application \
"