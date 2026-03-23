#!/usr/bin/env bash

# USER VARIABLES
NODES=${1:-1}
NTASKS_PER_NODE=${2:-1}
GPU_PER_TASK=${3:-1}

task_dir=$(dirname "$(readlink -f "$0")")

# Note: Agent should append preset flags automatically when generating this file
launch-slurm-workers \
    $task_dir \
    --nodes $NODES \
    --ntasks-per-node $NTASKS_PER_NODE \
    --gpu-per-task $GPU_PER_TASK \
    --yes
