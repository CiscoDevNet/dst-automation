#!/bin/sh

NAME=dst-automation
IMAGE=dst-image

cache=""
denv=""

# Set the DST_DEV variable to trigger a full build of the image.
if [ -n "${DST_DEV}" ]; then
  cache="--no-cache --pull"
fi

if [ $# = 1 -a x"$1" = x"-deploy" ]; then
  denv="-e DO_DEPLOY=1"
fi

docker stop ${NAME} >/dev/null 2>&1

printf "Building Docker image for DST Automation..."
docker build ${cache} -t ${IMAGE} . > /dev/null
if [ $? = 0 ]; then
  echo "DONE."
  docker run --rm -it ${denv} --name=${NAME} ${IMAGE}
else
  echo "FAILED."
fi
