#!/bin/bash

source ~/.bashrc
conda activate /opt/disk2/env-gpt-voice

thisFileDir="$( cd "$( dirname "${BASH_SOURCE[0]}")" && pwd )"

cd $thisFileDir
nohup uvicorn web:app --reload --host 0.0.0.0 --port 5012 >> nohup.out &