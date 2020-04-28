#!/bin/sh


echo "################## Executing Dynamic Split Tunnel Test #######################"
echo
python ./test_dst.py
rc=$?
echo
echo "################## Dynamic Split Tunnel Test Complete ########################"

if [ x"${DO_DEPLOY}" = x"1" -a ${rc} = 0 ]; then
  echo "########### Deploying Dynamic Split Tunnel Config To Production ##############"
  echo
  python ./deploy_dst.py
  echo
  echo "##################### Production Deployment Complete #########################"
fi
