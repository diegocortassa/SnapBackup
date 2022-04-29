#!/usr/bin/env python
# -*- coding:utf-8 -*-
#
# Snapshot like Backup using rsync and hard links
#
# Based on information from the article "Easy Automated Snapshot-Style Backups with Linux and Rsync", by Mike Rubel
# http://www.mikerubel.org/computers/rsync_snapshots/
#
# crontab configuration example:
# ############
# 00 8-18 *  *  1-5 root python snapback.py --name mybackup --tag hourly --keep 8 /my/files /snapshots_dir
# 00 21   *  *  1-5 root python snapback.py --name mybackup --tag daily --keep 20 /my/files /snapshots_dir
# 00 21   *  *  6   root python snapback.py --name mybackup --tag weekly --keep 4 /my/files /snapshots_dir
# 00 21   *  *  7   root [ $(date +\%d) -le 07 ] && python snapback.py --name mybackup --tag monthly --keep 6 /my/files /snapshots_dir
#

import argparse
import glob
import subprocess
import logging
import fcntl
import sys
import shutil
import os
import platform
import time

exit_code = 0


def main():

    if platform.system().lower() != "linux":
        logging.error("This script uses hard links and can only be used on linux")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Snapshot like Backup using rsync and hard links")
    parser.add_argument("--name", help="Backup name", required=True)
    parser.add_argument("--tag", help="Backup tag", required=True)
    parser.add_argument("--keep", dest="keep", help="How many snapshots to keep", type=int, default=0)
    parser.add_argument("--excludes", help="Rsync excludes", nargs='+', default=[])
    parser.add_argument("source", help="Source dir")
    parser.add_argument("dest", help="Directory in which the backup snapshots will be created")

    args = parser.parse_args()

    configure_logging()

    logging.info("Starting")
    start_time = time.time()

    # Lock file
    lock_file = "/tmp/snapback_{}.lock".format(args.name)
    try:
        fp = open(lock_file, "w")
        fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logging.error("Another backup instance for '{}' is running".format(args.name))
        logging.error("or delete stale lock file '{}'".format(lock_file))
        logging.error("Backup operation skipped")
        sys.exit(1)

    if not os.path.exists(args.dest):
        os.makedirs(args.dest)
    elif not os.path.isdir(args.dest):
        logging.error("{} is not a directory".format(args.dest))
        sys.exit(1)

    logging.info("Calling sync")
    res = sync(source=args.source, dest=args.dest, name=args.name, tag=args.tag, excludes=args.excludes)
    logging.info("Calling rotate")
    rotate(dest=args.dest, name=args.name, tag=args.tag, keep=args.keep)

    # Remove lock file
    os.remove(lock_file)

    elapsed_time = time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))
    logging.info("Finished")
    logging.info("Elapsed time: %s" % elapsed_time)

    sys.exit(res)


def configure_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    if "DEBUG" in os.environ:
        formatter = logging.Formatter('%(asctime)s %(levelname)-8s|%(module)s.%(funcName)s (%(lineno)d)> %(message)s', '%Y-%m-%d %H:%M:%S')
    else:
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(module)s %(message)s', '%Y-%m-%d %H:%M:%S')

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)

    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.addHandler(error_handler)


def launch_command(cmd_line):
    """
    Launch cmd_line printing piped output

    :param cmd_line: string command to be launched
    :return: int return code of the launched command
    """

    # output = subprocess.check_output(cmd_line, stderr=subprocess.STDOUT)
    pipe = subprocess.Popen(cmd_line, stdout=subprocess.PIPE, universal_newlines=True)
    with pipe.stdout:
        for line in iter(pipe.stdout.readline, ''):
            logging.info("{}: {}".format(cmd_line[0], line.rstrip('\n')))
    return_code = pipe.wait()  # wait for the command to finish and get return code

    if return_code > 0:
        logging.error("ERROR returned by %s" % " ".join(cmd_line))

    return return_code


def touch(path):
    """
    Equivalent to unix touch

    :param path: string file or directory path
    :return: nothing
    """
    logging.info("Touching %s" % path)
    if os.path.isdir(path):
        os.utime(path, None)
    else:
        with open(path, 'a'):
            os.utime(path, None)


def rotate(dest=None, name=None, tag=None, keep=-1):
    """
    Remove older backups
    :param dest: dir containing backups
    :param name: backup name
    :param tag: backup tag
    :param keep: int: how many snapshots to keep
    """

    # lowest significant keep value is 1
    if keep < 1:
        return

    search_glob = os.path.join(dest, "snapback_{}_*_{}".format(name, tag))
    snapshots_list = sorted(glob.glob(search_glob))
    delete_list = snapshots_list[:-keep]

    for snapshot in delete_list:
        logging.info("Deleting {}".format(snapshot))
        shutil.rmtree(snapshot)


def sync(source=None, dest=None, name=None, tag=None, excludes=None):
    """
    Executes rsync
    :param source: Source directory
    :param dest: Directory in which the backup snapshots will be created
    :param name: Backup snapshot base name (es. mybackup)
    :param tag: Backup snapshot tag name (es. daily)
    :param excludes: rsync excludes list
    :return: command exit code
    """

    if excludes is None:
        excludes = []

    timestamp = time.strftime("%Y%m%d%I%M%S")

    current_snapshot = os.path.join(dest, "snapback_{}_{}_{}".format(name, timestamp, tag))

    search_glob = os.path.join(dest, "snapback_{}_*_{}".format(name, tag))
    snapshots_list = sorted(glob.glob(search_glob))
    if len(snapshots_list):
        last_snapshot = snapshots_list[-1]
        logging.info("Copy-linking %s to %s" % (last_snapshot, current_snapshot))
        cmd_line = ["cp", "-a", "-l", last_snapshot, current_snapshot]
        result = launch_command(cmd_line)
        if result > 0:
            logging.error("Errors copy-linking %s" % source)
            return result

    # Make sure src end with a / to make sure
    # we are going to backup the source following symlinks
    source = source.rstrip("/") + "/"

    current_snapshot += "/"

    if not os.path.exists(dest):
        os.makedirs(dest)

    cmd_line = ['rsync', "-va", "--human-readable", "--delete", "--delete-excluded"]

    for exclude in excludes:
        cmd_line.append("--exclude=%s" % exclude)

    cmd_line.append(source)
    cmd_line.append(current_snapshot)

    logging.info("Syncing %s to %s" % (source, current_snapshot))
    result = launch_command(cmd_line)
    if result > 0:
        logging.error("Errors syncing %s" % source)
        return result

    # Update date on current snapshot directory
    touch(current_snapshot)
    date = time.strftime("%Y%m%d_%I%M%S")
    date_file = os.path.join(current_snapshot, "_backup_%s" % date)
    touch(date_file)

    return 0


if __name__ == '__main__':
    main()
