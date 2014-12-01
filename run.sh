#!/bin/bash
pwd=`pwd`
export PATH=${pwd}/tools/install/bin:$PATH
export LD_LIBRARY_PATH=${pwd}/tools/install/lib:$LD_LIBRARY_PATH
python run.py

