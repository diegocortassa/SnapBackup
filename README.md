# SnapBack
SnapBack is a simple to use backup script using hard links and rsync to deduplicate files allowing for quick and efficient "snapshot like" backups

SnapBack is based on information from the article "Easy Automated Snapshot-Style Backups with Linux and Rsync", by Mike Rubel
http://www.mikerubel.org/computers/rsync_snapshots/

## Do NOT edit files in snapshots
Files in snapshots are hardlinked, edits on a file will change the same file in all snapshots!

Keep snapshots in a read only share

#### Usage:
```
usage: snapback.py [-h] --name NAME --tag TAG [--keep KEEP] [--excludes EXCLUDES [EXCLUDES ...]] source dest

Snapshot like Backup using rsync and hard links

positional arguments:
  source                Source dir
  dest                  Directory in which the backup snapshots will be created

options:
  -h, --help            show this help message and exit
  --name NAME           Backup name
  --tag TAG             Backup tag
  --keep KEEP           How many snapshots to keep
  --exclude EXCLUDE     Passed to rsync exclude, you may use as many --exclude options on the command line as you like
```

#### crontab configuration example:
```
00 8-18 *  *  1-5 root python snapback.py --name mybackup --tag hourly --keep 8 /my/files /snapshots_dir
00 21   *  *  1-5 root python snapback.py --name mybackup --tag daily --keep 20 /my/files /snapshots_dir
00 21   *  *  6   root python snapback.py --name mybackup --tag weekly --keep 4 /my/files /snapshots_dir
00 21   *  *  7   root [ $(date +\%d) -le 07 ] && python snapback.py --name mybackup --tag monthly --keep 6 /my/files /snapshots_dir
```
