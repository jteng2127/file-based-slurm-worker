#!/usr/bin/env bash

task_dir=$(dirname "$(readlink -f "$0")")

launch-slurm-workers \
    $task_dir \
    --nodes 2 \
    --ntasks-per-node 2 \
    --gpu-per-task 2 \
    --task-estimate-second $((1 * 60))
