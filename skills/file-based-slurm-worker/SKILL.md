---
name: file_based_slurm_worker
description: Handles operations for the file-based-slurm-worker CLI tool, including task generation, Slurm worker deployment, and site-specific platform detection. Load this skill when you need to run long experiments, multiple experiments, or heavy GPU tasks on a Slurm cluster.
metadata:
  version: v2026.03.23-4
  source: https://github.com/jteng2127/file-based-slurm-worker/tree/main/skills/file-based-slurm-worker
---

# File-Based Slurm Worker (Agent Guide)

## 1. Lazy Installation & Environment Setup
- **Trigger Protocol:** If `launch-slurm-workers` command fails with `command not found` during execution, the agent MUST ask the user for an installation path (default: `~/`) and execute:
  ```bash
  git clone https://github.com/jteng2127/file-based-slurm-worker.git <INSTALL_PATH>
  bash <INSTALL_PATH>/install
  source ~/.bashrc # or ~/.zshrc
  ```
## 2. How it works

Tasks are shell scripts placed in a `1_pending/` directory. Workers race to pick them up, move them through a set of numbered state directories, and log their output.

```
task-dir/
  1_pending/        task scripts (.sh) waiting to run
  2_running/        task currently being executed (moved here atomically)
  3_done/           completed tasks (exit code 0)
  4_failed/         failed tasks (non-zero exit code)
  5_task_logs/      stdout/stderr for each task run
  6_job_logs/       Slurm job logs
  7_worker_status/  one file per active worker with current status
```

Multiple workers poll `1_pending/` concurrently. A task file is claimed by `mv` it into `2_running/`, which is atomic on most filesystems, so each task runs on exactly one worker.

If a worker is terminated (received SIGTERM or SIGINT) while running a task, the task file is moved back to `1_pending/` automatically, so it will be retried by any remaining worker.

## 3. Global Job Presets (Metadata Registry)
- **Path:** `<workspace>/file-based-slurm-workers/slurm_worker_presets.yaml`.
- **Function:** Stores multiple named configurations in a single YAML file for central retrieval.
- **Constraints:** Use ONLY long arguments (e.g., `--nodes`, not `-N`).
- **Exclusion:** `nodes`, `ntasks-per-node`, and `gpu-per-task` must be excluded from the preset file and provided as shell variables in `launch.sh`.
- **See Assets:** Reference `assets/slurm_worker_presets.yaml` for a starter template including:
  - `nano4_H100_failsafe`: (Includes failsafe flags: `max-consecutive-fails`, `reset-failed`, `log-system-metrics`).
  - `nano5_H100` (normal partition).
  - `nano5_H200` (normal2 partition).
  - `twcc_V100` (gp4d partition).

## 4. Operational Workflow

### Phase A: Synthesis

#### 1. Resource Mathematics & Worker Mapping
Before writing any controllers, calculate array bounds to prevent resource overallocation:
- **`nodes` (`N`)**: Total independent servers requested.
- **`ntasks_per_node` (`n`)**: Number of parallel workers on *each* node.
- **`gpu_per_task` (`g`)**: GPUs assigned exclusively to *each* worker.
- **Parallel Scale:** Total workers processing the queue = `N * n`.
- **Hard Hardware Limit:** `n * g` MUST NOT exceed the maximum physical GPUs available on the selected node partition. A violation will cause Slurm to hang immediately.

#### 2. Asset & Controller Setup
1. **Asset Retrieval:** Create a new `TASK_DIR` based on the current context, default in your workspace. Copy `gen.py` and `launch.sh` from the skill `assets/` folder into this new `TASK_DIR`. Copy `slurm_worker_presets.yaml` to the workspace if it is missing.
2. **Controller Setup:**
   - Customize `gen.py` to define the specific job logic (CPU/GPU workloads).
   - Customize `launch.sh` to inject the selected preset's long flags and define `<nodes>`, `<ntasks_per_node>`, and `<gpu_per_task>` as top-level shell variables. Note that the preset YAML is only for reference when creating this `launch.sh` file.

### Phase B: Deployment
1. **Task Population:**
   - Execute `python gen.py`. This automatically initializes `0_gen/` and `1_pending/`.
   - **Verification:** The agent must inspect a subset of scripts in `0_gen/` manually to verify script syntax and resource mapping before proceeding.
   - **Staging:** `mv 0_gen/*.sh 1_pending/`.
2. **Worker Ignition:** Execute `bash launch.sh <nodes> <ntasks_per_node> <gpu_per_task>`. (Always assure the underlying `launch-slurm-workers` call utilizes `--yes` to skip safety prompts).

### Phase C: Monitoring & Result Evaluation
This phase is engaged either by a scheduled background check or an explicit user request.

1. **Queue Inspection:** Check directory distribution (e.g., `ls 3_done | wc -l`, `ls 4_failed | wc -l`) to determine completion ratio. Watch task states via the directory layout (`2_running/`, `3_done/`, `4_failed/`, etc.).
2. **Log Audit:** 
   - **Task Context:** If tasks land in `4_failed/`, query the corresponding stdout/stderr logs in `5_task_logs/` to diagnose the root cause.
   - **Worker Infrastructure Context:** For node-level debugging, inspect `6_job_logs/`. It contains `<jobid>-worker.log` (central sbatch initialization logic) and `<jobid>-worker-worker.log` (chronological actions of every worker including task starts, completions, fails, and idle timeouts).
3. **Control Operations:**
   - Stop all workers gracefully for a job: `scancel <JOB_ID>`
   - Stop a specific worker gracefully: `rm task-dir/7_worker_status/<WORKER_ID>`
   - Stop a task by moving the script out of `2_running/`
   - Workers can auto-terminate if they fail too many consecutive tasks. Enable this with `launch-slurm-workers --max-consecutive-fails MAX`.
4. **Recovery Implementation:** 
   - Move tasks back to pending everytime it failed: `launch-slurm-workers --reset-failed TASK_DIR` or manually `mv task-dir/4_failed/*.sh task-dir/1_pending/`

## 5. Site-Specific Platform Specs
The agent can identify the current environment using `hostname` and adjust configurations accordingly.

**Out-of-Sync Verification Protocol:** If the agent encounters unexpected Slurm errors, jobs that fail to start, or suspects the specs below are outdated, it MUST execute the following command to re-verify the platform matrix:
```bash
sacctmgr show assoc where user=$USER && sacctmgr show qos && scontrol show partition -o && sinfo -N -o "%N %P %c %m %G" | head
```

### TWCC
- **Hostname Pattern:** `un-ln*`.
- **Hardware Architecture (Per Node):**
  - **GPUs:** 8x V100 (`gpu:8`)
  - **CPUs:** 36 Cores
  - **Memory:** ~772 GB RAM (`772400 MB`)
- **Queue Definitions & User Limits:**
  - **`gp1d` Partition:**
    - **Time Limit (`MaxWall`):** 1 day (`1-00:00:00`).
    - **Account Limits (`QoS: normal`):** Max 20 concurrent jobs per account (`MaxJobsPA`), Max 40 GPUs total per account (`MaxTRESPA`).
  - **`gp2d` Partition (Default):**
    - **Time Limit (`MaxWall`):** 2 days (`2-00:00:00`).
    - **Account Limits (`QoS: normal`):** Max 20 concurrent jobs per account (`MaxJobsPA`), Max 40 GPUs total per account (`MaxTRESPA`).
  - **`gp4d` Partition:**
    - **Time Limit (`MaxWall`):** 4 days (`4-00:00:00`).
    - **Account Limits (`QoS: for_gp4d`):** Max 20 concurrent jobs per account (`MaxJobsPA`), Max 80 GPUs total allocated per account (`MaxTRESPA: gres/gpu=80`).
  - **`express` Partition:**
    - **Time Limit (`MaxWall`):** 4 days (`4-00:00:00`).
    - **Account Limits (`QoS: for_express`):** Max 20 concurrent jobs per account (`MaxJobsPA`), Max 256 GPUs total allocated per account (`MaxTRESPA: gres/gpu=256`).
- **Worker Configuration Rules:**
  - **Max GPUs:** `n * g` MUST scale up to exactly equal `<= 8`.
  - **Optimal CPU Scaling:** Exact mapping is 4 CPUs per GPU (36 cores ÷ 8 GPUs).
  - **Memory:** ~96 GB RAM per GPU available loosely.

### Nano4
- **Hostname Pattern:** `25a-lgn*`.
- **Hardware Architecture (Per Node):**
  - **GPUs:** 8x H200 (`gpu:H200:8`)
  - **CPUs:** 112 Cores
  - **Memory:** ~1.9 TB RAM (`1900000 MB`)
- **Queue Definitions & User Limits:**
  - **`dev` Partition (Default):**
    - **Time Limit (`MaxWall`):** 2 hours (`02:00:00`).
    - **Account Limits (`QoS: p_dev`):** Max 20 concurrent jobs per user (`MaxJobsPU`), Max 10 submissions per user (`MaxSubmitPU`).
  - **`normal` Partition:**
    - **Time Limit (`MaxWall`):** 1 day (`1-00:00:00`).
    - **Account Limits (`QoS: p_normal`):** Max 10 concurrent jobs per user (`MaxJobsPU`), Max 10 submissions per user (`MaxSubmitPU`), Max 320 GPUs total allocated per account (`MaxTRESPA: gres/gpu=320`).
    - **Min Resource:** `MinTRES: gres/gpu=16` (QoS requirement).
- **Worker Configuration Rules:**
  - **Max GPUs:** `n * g` MUST scale up to exactly equal `<= 8`. (Nodes physically max at 8 GPUs).
  - **Optimal CPU Scaling:** 14 CPUs mapped per GPU (112 cores ÷ 8 GPUs).
  - **Memory:** `DefMemPerGPU=204800` (~200 GB RAM is hard-allocated per individual GPU requested).

### Nano5
- **Hostname Pattern:** `cbi-lgn*`.
- **Hardware Architecture (Per Node):**
  - **GPUs:** 8x H100 or H200 (Partition dependent)
  - **CPUs:** 112 Cores
  - **Memory:** ~1.9 TB RAM (`1900000 MB`)
- **Queue Definitions & User Limits:**
  - **`dev` Partition (H100 GPUs):**
    - **Time Limit (`MaxWall`):** 1 hour (`01:00:00`).
    - **Node Limits:** Max 1 node requested per job.
    - **Account Limits (`QoS: p_dev`):** Max 2 concurrent jobs per user (`MaxJobsPU`), Max 8 GPUs total per account (`MaxTRESPA`).
  - **`normal` Partition (H100 GPUs):**
    - **Time Limit (`MaxWall`):** 2 days (`2-00:00:00`).
    - **Node Limits:** Max 2 nodes requested per job. 
    - **Account Limits (`QoS: p_normal`):** Max 2 concurrent jobs per user (`MaxJobsPU`), Max 16 GPUs total per account (`MaxTRESPA`).
  - **`4nodes` Partition (H100 GPUs):**
    - **Time Limit (`MaxWall`):** 1 day (`1-00:00:00`).
    - **Node Limits:** Max 4 nodes requested per job.
    - **Account Limits (`QoS: p_4nodes`):** Max 2 concurrent jobs total per account (`MaxJobsPA`), Max 32 GPUs total per account (`MaxTRESPA`).
  - **`normal2` Partition (H200 GPUs):**
    - **Time Limit (`MaxWall`):** 2 days (`2-00:00:00`).
    - **Node Limits:** Max 2 nodes requested per job. 
    - **Account Limits (`QoS: p_normal`):** Max 2 concurrent jobs per user (`MaxJobsPU`), Max 16 GPUs total per account (`MaxTRESPA`).
- **Worker Configuration Rules:**
  - **Max GPUs:** `n * g` MUST scale up to exactly equal `<= 8`.
  - **Optimal CPU Scaling:** Exact mapping is 14 CPUs per GPU (112 cores ÷ 8 GPUs).
  - **Memory:** No `DefMemPerGPU` hard limit encoded in SLURM; rely on `~237 GB` RAM available loosely per GPU.

## 6. How to... (Advanced Flag Tips)

For a complete command reference, you can run `launch-slurm-workers --help`.

### I don't want to confirm submition when running `launch-slurm-workers`
Use `-y` or `--yes` to skip confirmation prompt.

### How to automatically move failed tasks back to pending / clean up logs?
Use `--reset-failed` and `--clean-logs` to automatically move failed tasks back to pending / clean up logs before submitting sbatch.

`--reset-failed` also instructs each worker to put any newly failed tasks back to `1_pending/` immediately (instead of `4_failed/`), so failed tasks are continuously retried by any available worker for the duration of the job.

I don't recommend cleaning up logs automatically, as it may be useful for debugging.

### How to pass/override sbatch args?
Use `--sb--long-arg <value>` or `--sb-s <value>` for short args. You can check if the overrides are correct when confirming submition.

### If the Slurm job is almost reaching the time limit, how to make the worker stop accepting new tasks?
Use `--task-estimate-second <value>` to set the estimated time of each task. Then the worker will stop accepting new tasks when the remaining slurm time is less than the estimated time. It will still continue running the task it already started.

### How to log system metrics and top process (CPU, Memory) before task start? I suspect someone is using my resources.
Use `--log-system-metrics` so that the worker will log GPU, CPU, Memory, Virtual memory, Top processes by CPU, and Top processes by memory before every task.

### How to prevent broken worker (e.g. node lack of virtual memory, node GPU or CUDA broken) from keep failing all my tasks?
Use `--max-consecutive-fails 3`, then the worker will: 
- stop after 3 consecutive failures (highly likely the problem is coming from worker)
- automatically put the failed tasks back to `1_pending/`

### I want my worker timeout after idle for X seconds
Use `-i X` or `--max-idle X` with `launch-slurm-workers`.
