#!/bin/bash
AROMA_PACKAGE=${AROMA_PACKAGE:-"git+https://github.com/web3chan/aroma.git@develop"}
WEB3CHAN_PACKAGE=${WEB3CHAN_PACKAGE:-"git+https://github.com/web3chan/web3chan.git@master"}
IMAGE_NAME=${IMAGE_NAME:-"web3chan"}
newcontainer=$(buildah from debian)
buildah run $newcontainer -- apt update
buildah run $newcontainer -- apt install -y --no-install-recommends python3 python3-pip git
buildah run $newcontainer -- apt clean
buildah run $newcontainer -- pip install $AROMA_PACKAGE
buildah run $newcontainer -- pip install $WEB3CHAN_PACKAGE orm[postgresql]
buildah config --user nobody:nogroup $newcontainer
buildah config --port 18166 $newcontainer
buildah config --cmd '"/usr/bin/python3" "-m" "web3chan" "-d"' $newcontainer
buildah commit $newcontainer $IMAGE_NAME