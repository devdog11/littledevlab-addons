ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip curl \
    && pip3 install --no-cache-dir --break-system-packages uv

COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
