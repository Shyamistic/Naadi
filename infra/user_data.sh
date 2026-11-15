#!/bin/bash
# Boot script for the Naadi server (Amazon Linux 2023, arm64).
# Installs the feed recorder and ETA baseline logger as systemd services and
# syncs their output to S3 every 10 minutes. __BUCKET__ is replaced at launch.
set -euxo pipefail
BUCKET=__BUCKET__
REGION=ap-south-1
APP=/opt/naadi

dnf install -y python3.11 python3.11-pip
id naadi || useradd --system --create-home --home-dir "$APP" --shell /sbin/nologin naadi
mkdir -p "$APP/data/raw" "$APP/delhi_buses_static_gtfs_v1-2"
aws s3 cp "s3://$BUCKET/code/" "$APP/" --recursive --region "$REGION" --only-show-errors
aws s3 cp "s3://$BUCKET/static/delhi_buses_static_gtfs_v1-2/" "$APP/delhi_buses_static_gtfs_v1-2/" --recursive --region "$REGION" --only-show-errors
python3.11 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --quiet --upgrade pip
"$APP/.venv/bin/pip" install --quiet -r "$APP/infra/requirements-server.txt"

OTD=$(aws ssm get-parameter --region "$REGION" --name /naadi/OTD_API_KEY --with-decryption --query Parameter.Value --output text)
ETA=$(aws ssm get-parameter --region "$REGION" --name /naadi/ETA_API_KEY --with-decryption --query Parameter.Value --output text)
umask 077
printf 'OTD_API_KEY=%s\nETA_API_KEY=%s\n' "$OTD" "$ETA" > "$APP/.env"
umask 022
chown -R naadi:naadi "$APP"

for svc in feed:record_feed eta:log_eta_baseline; do
  name=${svc%%:*}; script=${svc##*:}
  cat > "/etc/systemd/system/naadi-$name.service" <<EOF
[Unit]
Description=Naadi $script
After=network-online.target
Wants=network-online.target

[Service]
User=naadi
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -u $APP/scripts/$script.py
Restart=always
RestartSec=15
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF
done

cat > /usr/local/bin/naadi-sync <<EOF
#!/bin/bash
set -uo pipefail
aws s3 sync $APP/data/raw s3://$BUCKET/raw --region $REGION --only-show-errors --exclude '*.log' --exclude '*.pid'
# Keep the disk small: drop local copies once they are older than 3 days (already in S3).
find $APP/data/raw -name '*.parquet' -mtime +3 -delete
find $APP/data/raw -name '*.pb' -mtime +1 -delete
EOF
chmod 755 /usr/local/bin/naadi-sync

cat > /etc/systemd/system/naadi-sync.service <<EOF
[Unit]
Description=Sync Naadi data to S3

[Service]
Type=oneshot
ExecStart=/usr/local/bin/naadi-sync
EOF

cat > /etc/systemd/system/naadi-sync.timer <<EOF
[Unit]
Description=Sync Naadi data to S3 every 10 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
EOF

# Cap journald so logs never fill the disk.
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=200M\n' > /etc/systemd/journald.conf.d/naadi.conf
systemctl restart systemd-journald

systemctl daemon-reload
systemctl enable --now naadi-feed.service naadi-eta.service naadi-sync.timer
echo "naadi bootstrap done"
