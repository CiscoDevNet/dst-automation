#!/bin/sh

NAME=dst-test
IMAGE=dst-image

docker stop ${NAME} >/dev/null 2>&1

printf "Building Docker image for testing..."
docker build --no-cache --pull -t ${IMAGE} -f Dockerfile.test . > /dev/null
echo "DONE."
if [ $? = 0 ]; then
    docker run --rm -it --name=${NAME} ${IMAGE}
fi
