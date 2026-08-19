# Production DB Backup Runbook (go2fresh-1)

Nightly automated PostgreSQL backup for the attendance system.
**Installed and verified: 2026-08-19.**

All production data (employees, attendance logs, config, everything) lives in the
`db` container's `pgdata` Docker volume. This backup exists because that volume is
otherwise the only copy — and Taiwan LSA §30(5) requires 5-year attendance-record
retention.

## Current state (what is already set up)

| Item | Value |
|------|-------|
| Backup script | `/root/backup-attendance.sh` on go2fresh-1 |
| Schedule | root's crontab, `30 3 * * *` (03:30 AM, server clock is CST +0800) |
| Output | `/home/gogoffccict/db-backups/attendance_YYYY-MM-DD.sql.gz` (~63 KB gzipped) |
| Log | `/var/log/attendance-backup.log` (one `backup OK (<bytes>)` line per run) |
| Rotation | keeps 30 daily dumps; 1st-of-month dumps kept ~370 days |

The script runs as root (via root's crontab) because the deploy user
`gogoffccict` is not in the docker group — root needs no `sudo` inside cron.

## How it was set up (repeatable, step by step)

All steps in an SSH session: `ssh gogoffcc_internal`
(**office network only** — the server does not accept SSH from home/WFH).

### 1. Create the script

```bash
sudo tee /root/backup-attendance.sh > /dev/null <<'EOF'
#!/bin/sh
set -e
BACKUP_DIR=/home/gogoffccict/db-backups
COMPOSE_DIR=/home/gogoffccict/gogofresh-attendance

mkdir -p "$BACKUP_DIR"
cd "$COMPOSE_DIR"

docker compose -f docker-compose.prod.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "$BACKUP_DIR/attendance_$(date +%F).sql.gz"

# Sanity check: a healthy gzipped dump is never tiny
size=$(stat -c%s "$BACKUP_DIR/attendance_$(date +%F).sql.gz")
[ "$size" -gt 1000 ] || { echo "BACKUP TOO SMALL ($size bytes)"; exit 1; }

# Rotation: keep 30 daily dumps; keep 1st-of-month dumps ~1 year
find "$BACKUP_DIR" -name 'attendance_*.sql.gz' -mtime +30 ! -name '*-01.sql.gz' -delete
find "$BACKUP_DIR" -name 'attendance_*-01.sql.gz' -mtime +370 -delete

echo "$(date '+%F %T') backup OK ($size bytes)"
EOF
sudo chmod 700 /root/backup-attendance.sh
```

Why it looks this way:

- `exec -T` — required because output is piped (no pseudo-TTY, keeps the SQL clean).
- The inner `"$POSTGRES_USER"` / `"$POSTGRES_DB"` read the **container's own** env
  vars, so the script works regardless of the actual names.
- Dumps land in `gogoffccict`'s home so they can be pulled by `scp` without sudo.

### 2. Test it once

```bash
sudo /root/backup-attendance.sh
ls -lh /home/gogoffccict/db-backups/
zcat /home/gogoffccict/db-backups/attendance_$(date +%F).sql.gz | grep -c "PostgreSQL database dump complete"
```

The `grep -c` must print `1`. (The dump file *ending* with a `\unrestrict <token>`
line is the normal PG 16 pg_dump footer, not an error — the "dump complete"
comment sits a few lines above it.)

### 3. Confirm the server timezone

```bash
date        # must show CST +0800 → cron's 03:30 means 3:30 AM Taiwan time
```

### 4. Install the cron job

```bash
sudo crontab -e     # first run asks for an editor — pick 1 (nano)
```

Add this line at the bottom, save (Ctrl+O, Enter), exit (Ctrl+X):

```
30 3 * * * /root/backup-attendance.sh >> /var/log/attendance-backup.log 2>&1
```

Verify:

```bash
sudo crontab -l          # the line above must appear
systemctl is-active cron # must print: active
```

### 5. Verify the first unattended run (next morning)

```bash
tail /var/log/attendance-backup.log
ls -lh /home/gogoffccict/db-backups/
```

Expect a `backup OK (<bytes>)` line and a new dated `.sql.gz`. The only realistic
cron-specific failure is `docker` missing from cron's PATH — the log would say so
explicitly.

## Routine operations

### Health check (any time)

```bash
tail /var/log/attendance-backup.log
ls -lh /home/gogoffccict/db-backups/
```

The logged byte size makes a silently-shrinking database visible at a glance.

### Pull a dump to the local Windows machine

From **local PowerShell** (not inside SSH), office network, in the destination folder:

```powershell
scp gogoffcc_internal:~/db-backups/attendance_2026-08-19.sql.gz .
```

The laptop cannot resolve the bare hostname `go2fresh-1`; the SSH config alias
`gogoffcc_internal` supplies the real host + user, and `scp` reads the same config.

### Restore (disaster recovery)

Restore **through `psql`** into an empty DB (other tools may choke on the PG 16
`\restrict`/`\unrestrict` meta-commands). On the server, in
`~/gogofresh-attendance`:

```bash
zcat attendance_YYYY-MM-DD.sql.gz | sudo docker compose -f docker-compose.prod.yml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

### Quarterly restore test (recommended)

Restore the latest dump into a scratch local Postgres and spot-check
`SELECT count(*) FROM attendance_logs;`. A backup that has never been restored
is a hope, not a backup.

## Open follow-up

- **Off-server copy** — the server's disk currently holds every copy. Options:
  - Weekly Windows Task Scheduler job on the office machine running the `scp`
    pull above (fails harmlessly on WFH days; server keeps 30 dailies anyway).
  - `rclone` on the server pushing each dump to cloud storage (needs a one-time
    interactive `rclone config`).
