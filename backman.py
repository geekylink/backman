#!/bin/python
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>
###############################################################################x

import os
import sys
import json
import argparse
from time import sleep
from subprocess import Popen, PIPE, STDOUT, TimeoutExpired

def getConfirmation(msg: str = "y/n: ", noStr: str = "", yesStr: str = ""): 
    """
        Asks user a yes/no question, 
        returns only 'y' or 'n'
    """
    ans = "?"
    while ans != "y":
        ans = input(msg)

        if ans == "n":
            if noStr:
                print(noStr)
            return ans

        if ans != "y":
            print("Invalid response. Try again.")

    if yesStr:
        print(yesStr)

    return ans

def askUser(msg: str, options):
    """
        Asks user msg
        User must pick one of options to continue
        returns user choice from options
    """
    ans = ""
    while ans not in options:
        ans = input(msg)

        if ans not in options:
            print("Invalid response. Try again.")

    return ans

def RunCMD(cmd: str, timeout = 15):
    """
        Runs a command, captures stdout & stderr, trims output
        timeout: how long to let command run, -1 for infinite
    """

    proc = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)

    try:
        if timeout == -1:
            outs, errs = proc.communicate()
        else:
            outs, errs = proc.communicate(timeout=timeout)
    except TimeoutExpired:
        proc.kill()
        outs, errs = proc.communicate()

    outs = outs.decode("UTF-8").strip()
    errs = (errs.decode("UTF-8").strip() if errs else None)

    return {"out": outs, "err": errs, "ret": proc.returncode}

def IsZFSReady():

    return (RunCMD("zpool status")["out"] != "no pools available")

def MountZFS(pool: str):
    """ TODO: improve this shit """
    # TODO:
    print("Importing volume...")
    zfsImport = RunCMD("sudo zpool import " + pool)
    if zfsImport["out"] == "":
        print("Mounting volumes...")

        zfsRet = os.system("sudo zfs mount -la") # Must be os.system for password auth
        print(zfsRet, zfsRet == 0)
        return (zfsRet == 0)
    else:
        print("Error while mounting: ", zfsImport["out"])

    return False

def PrepareZFS():
    if not IsZFSReady():
        return MountZFS("bluedrive")

    return True

class CouldNotConnectException(Exception):
    """ Custom exception """

BACKOFF_MAX = 600 # 10 mins
def RsyncDir(srcHost: str, srcDir: str, destHost: str, destDir: str, dryRun: bool = False, retries: int = -1, backoff: bool = True, confirm: bool = False, delete: bool = False):
    """
        Python function to call rsync
        returns list of files changed (or if dryRun=True: to change)
    """

    tries = 0
    exBackoff = 4 # Seconds to wait till retry

    while tries < retries or retries == -1:
        if retries != -1:
            tries += 1

        cmd = "rsync -azv " + ("--dry-run " if dryRun else "")\
                            + ("--delete " if delete else "")  \
            + (srcHost + ":" if srcHost and srcHost != "" else "") + srcDir + " " \
            + (destHost + ":" if destHost and destHost != "" else "") + destDir

        print("CMD: " + cmd)

        firstLine = True
        i = 0
        res = RunCMD(cmd, -1)
        out, err, ret = res["out"].split("\n"), res["err"], res["ret"]

        if ret != 0:
            print("Connection error: " + res["out"])

            if confirm and getConfirmation("Try again? y/n: ", "Aborting") == "n":
                print("abort")
                return None

            if backoff:
                sleep(exBackoff)
                exBackoff *= 2
                if exBackoff > BACKOFF_MAX:
                    exBackoff = BACKOFF_MAX
            continue
            #raise CouldNotConnectException("Could not connect: " + res["out"])

        for line in out:
            if firstLine:
                firstLine = False
                continue
            i += 1
            if line == "":
                return out[1:i]

        return []

def RsyncDirPrint(srcHost: str, srcDir: str, destHost: str, destDir: str, dryRun: bool = False, retries: int = -1, backoff: bool = True, confirm: bool = False, delete: bool = False):
    """
        RsyncDir() wrapper that also prints out result, helper
    """
    changeFiles = RsyncDir(srcHost, srcDir, destHost, destDir, dryRun, retries, backoff, confirm, delete)
    
    if len(changeFiles) == 0:
        print("No files changed")
    else:
        print("Files changed:")
        for file in changeFiles:
            print(file)

    return changeFiles


def SafeSync(srcHost: str, srcDir: str, destHost: str, destDir: str):
    """
        Preform an rsync dry-run, gets list of files to add/update, if anything
        If so: ask user to confirm
    """
    changeFiles = RsyncDir(srcHost, srcDir, destHost, destDir, dryRun=True, backoff=False, confirm=True)

    if changeFiles == None:
        print("failed to get files")
        return False

    # None signals an error, otherwise it would be an empty list
    #if changeFiles == None:
    #    return False

    if len(changeFiles) == 0:
        print("No files to update.")
        return True
    else:
        print("The following files have changed since last sync:")
        for file in changeFiles:
            print(file)

        if getConfirmation("Sync files? y/n: ", "Not syncing") == "n":
            return False

        print("Syncing files...")
        RsyncDir(srcHost, srcDir, destHost, destDir, dryRun=False, backoff=False, confirm=True)
        return True
    return False

def SafeRemove(srcHost: str, srcDir: str, destHost: str, destDir: str):
    """
        Preform an rsync dry-run deletion, gets list of files to delete, if anything
        If so: ask user to confirm deletion
    """
    changeFiles = RsyncDir(srcHost, srcDir, destHost, destDir, dryRun=True, backoff=False, confirm=True, delete=True)

    if len(changeFiles) == 0:
        print("Nothing to remove")
        return True
    
    print("The following files are to be removed:")
    
    for file in changeFiles:
        print(file)

    if getConfirmation("Confirm DELETION? Cannot be undone. y/n: ", "Not deleting") == "n":
        return False

    return RsyncDir(srcHost, srcDir, destHost, destDir, backoff=False, confirm=True, delete=True) is not None

def SafeMirror(srcHost: str, srcDir: str, dstHost: str, dstDir: str):
    res = SafeSync(srcHost, srcDir, dstHost, dstDir)

    return True

def readFileMap(filename: str):
    """ 
        Reads json file path mapping config 
        Returns mirror file paths mapping
            Format: [ [srcHost, srcDir, dstHost, dstDir], .. ]
    """

    with open(filename) as file:
        cfg = json.load(file)

    # Build mirror of file paths array
    mirrorAr = []
    for host in cfg:
        srcHost = host["host"]

        for srcD in host["dirs"]:
            srcDir = srcD["src"]

            # Sync each source to each of its dests
            for dstD in srcD["dests"]:
                dstHost = dstD["host"]
                dstDir = dstD["dest"]

                mirrorAr.append([srcHost, srcDir, dstHost, dstDir])


    return mirrorAr

def printFileMap(mirrorAr, showId: bool = True):
    for i in range(len(mirrorAr)):
        srcHost, srcDir = mirrorAr[i][0], mirrorAr[i][1]
        dstHost, dstDir = mirrorAr[i][2], mirrorAr[i][3]
        if showId:
            print(i, srcHost, srcDir, dstHost, dstDir)
        else:
            print(srcHost, srcDir, dstHost, dstDir)

def InteractiveMode(mirrorAr):
    """
        interactive user mode, can mirror, delete, or just sync individual paths
    """
    # TODO: --no-confirm for interactive mode?

    while True:
        # Output list for --interactive mode to choose from
        print("File map to choose from:")
        printFileMap(mirrorAr)

        # Gets selection ID from user
        selId = -1
        while selId < 0 or selId > len(mirrorAr)-1:
            try:
                selId = input("Input id (or 'q' to quit): ")
                if selId == "q":
                    return
                selId = int(selId)
            except KeyboardInterrupt:
                print("\nGoodbye :(")
                sys.exit(0)
            except:
                pass

        # Sync just that selection

        srcHost = mirrorAr[selId][0]
        srcDir = mirrorAr[selId][1]
        dstHost = mirrorAr[selId][2]
        dstDir = mirrorAr[selId][3]

        ans = ""
        while ans != "d":
            ans = askUser("What do you want to do?\n\
\n's'ync - sync source files to remote\
\n'r'emote sync - sync remote files to source\
\n'c'lean - remove files on remote that no longer exist on source\
\n'd'one - Finished with this dir\
\n\nChoice: ", ["c", "s", "d", "r"])

            if ans == "c":
                SafeRemove(srcHost, srcDir, dstHost, dstDir)
            elif ans == "s":
                SafeSync(srcHost, srcDir, dstHost, dstDir)
            elif ans == "r":
                SafeSync(dstHost, dstDir, srcHost, srcDir)
            elif ans == "d":
                pass
            else:
                raise Exception("Invalid response from user!")

        #SafeMirror(srcHost, srcDir, dstHost, dstDir)

def AutoMode(mirrorAr, args):
    for i in range(len(mirrorAr)):
        srcHost, srcDir = mirrorAr[i][0], mirrorAr[i][1]
        dstHost, dstDir = mirrorAr[i][2], mirrorAr[i][3]

        if args.confirm:
            if args.mirror:
                if args.sync:
                    SafeSync(srcHost, srcDir, dstHost, dstDir)
                SafeSync(dstHost, dstDir, srcHost, srcDir)
            else:
                if args.sync:
                    SafeSync(srcHost, srcDir, dstHost, dstDir)
                if args.delete:
                    SafeRemove(srcHost, srcDir, dstHost, dstDir)
        else: # --no-confirm
            if args.sync:
                RsyncDirPrint(srcHost, srcDir, dstHost, dstDir)

            if args.mirror:
                RsyncDirPrint(dstHost, dstDir, srcHost, srcDir)
            elif args.delete:
                RsyncDirPrint(srcHost, srcDir, dstHost, dstDir, delete=True)

def parseArgs():
    """
        CLI args for program
            * Does validation for sanity check of arg combos
    """
    parser = argparse.ArgumentParser(description='Simple python wrapper for rsync to allow ease of many paths or an interactive experience with confirmation dialogs.')

    parser.add_argument('--no-confirm', dest='confirm', action='store_const',
                                const=False, default=True,
                                help='Skip any confirmation dialogs')

    parser.add_argument('--no-sync', dest='sync', action='store_const',
                                const=False, default=True,
                                help='Skip the initial sync src -> dst')

    parser.add_argument('--interactive', dest='interactive', action='store_const',
                                const=True, default=False,
                                help='Only update certain file paths based on user choice')

    parser.add_argument('--mirror', dest='mirror', action='store_const',
                                const=True, default=False,
                                help='Sync src -> dst, then dst -> src')

    parser.add_argument('--delete', dest='delete', action='store_const',
                                const=True, default=False,
                                help='Delete files on remote not on source (after sync, unless also --no-sync)')

    parser.add_argument('--map', dest='map', action='store',
                                default="filesMap.json",
                                help='Files to sync together (Default: filesMap.json)')

    args = parser.parse_args()

    # Arg validation

    if args.interactive and (args.mirror or args.delete or not args.sync):
        raise Exception("Cannot use --interactive with --mirror, --delete, or --no-sync")

    if args.mirror and args.delete:
        raise Exception("Cannot --delete and --mirror together")

    if not args.sync and not args.mirror and not args.delete:
        raise Exception("So do nothing?")

    return args

if __name__ == "__main__":
    args = parseArgs()

    # JSON File path map
    mirrorAr = readFileMap(args.map)

    # ZFS prep
    if not PrepareZFS():
        print("Aborting data sync")
        os.exit(1)

    if args.interactive:
        InteractiveMode(mirrorAr)
    else:
        AutoMode(mirrorAr, args)
