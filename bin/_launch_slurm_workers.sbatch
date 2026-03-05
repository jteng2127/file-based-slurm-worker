#!/bin/bash
# ========== SBATCH options ==========
# (output overridden by launch-slurm-workers via sbatch --output)

# ========= (DO NOT MODIFY) Shell Options ==========
set -eu

# ========== Config ==========
# Env vars provided by launch-slurm-workers: TASK_DIR, MAX_IDLE, GPU_PER_TASK

SRUN_MEM=$(($SLURM_MEM_PER_NODE / $SLURM_NTASKS_PER_NODE))
SRUN_CPU=$SLURM_CPUS_PER_TASK

# ========== (DO NOT MODIFY) Script Location ==========
SCRIPT_PATH="$(scontrol show job "$SLURM_JOB_ID" | awk -F= '/Command=/{print $2}' | head -n 1 | cut -d ' ' -f 1)"
SCRIPT_DIR=$(dirname "${SCRIPT_PATH}")
WORKER_BIN="${SCRIPT_DIR}/launch-worker"

echo "$(date '+%Y-%m-%d %H:%M:%S') Script dir: ${SCRIPT_DIR}"
echo "$(date '+%Y-%m-%d %H:%M:%S') Task dir: ${TASK_DIR}  Max idle: ${MAX_IDLE}s  GPU per task: ${GPU_PER_TASK}"

# ========== (DO NOT MODIFY) Main job ==========
SECONDS=0

TOTAL_WORKERS=$((SLURM_NNODES * SLURM_NTASKS_PER_NODE))
for task_id in $(seq 0 $((TOTAL_WORKERS - 1))); do
    set -x
    srun \
        --nodes=1 \
        --ntasks=1 \
        --gres=gpu:${GPU_PER_TASK} \
        --mem=${SRUN_MEM} \
        --cpus-per-task=${SRUN_CPU} \
        --output=${TASK_DIR}/6_job_logs/%j-%x-worker.log \
        --error=${TASK_DIR}/6_job_logs/%j-%x-worker.log \
        bash "${WORKER_BIN}" "${TASK_DIR}" "${MAX_IDLE}" &
    { set +x; } 2>/dev/null
done

# Monitor: cancel the job when all active workers are idle or gone
(
    WORKER_STATUS_DIR="${TASK_DIR}/7_worker_status"
    shopt -s nullglob

    # startup grace period to wait for workers to write status files
    sleep 60
    while true; do
        sleep 30
        STATUS_FILES=("$WORKER_STATUS_DIR/${SLURM_JOB_ID}".*)
        if [ ${#STATUS_FILES[@]} -eq 0 ]; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') No worker status files found. Cancelling job $SLURM_JOB_ID."
            scancel "$SLURM_JOB_ID"
            break
        fi
        ALL_IDLE=true
        for f in "${STATUS_FILES[@]}"; do
            if ! grep -q "IDLE" "$f" 2>/dev/null; then
                ALL_IDLE=false
                break
            fi
        done
        if $ALL_IDLE; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') All workers idle. Cancelling job $SLURM_JOB_ID."
            scancel "$SLURM_JOB_ID"
            break
        fi
    done
) &

wait

# ========== (DO NOT MODIFY) Job end message ==========
echo -e "\n========== Done. Runtime:$((SECONDS/3600)):$((SECONDS/60%60)):$((SECONDS%60)) ==========\n"
scontrol show job "$SLURM_JOB_ID"
echo "$SLURM_JOB_NAME end, job ID: $SLURM_JOB_ID"
