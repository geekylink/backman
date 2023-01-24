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

def readFileMap(filename: str):
    """ 
        Reads json file path mapping config 
        Returns mirror file paths mapping
            Format: [ [srcHost, srcDir, dstHost, dstDir], .. ]
    """

    with open(filename) as file:
        cfg = json.load(file)

    # Build mirror of file paths array
    mirrorMap = []
    mirrorMap.append([])
    mirrorHosts = []

    for host in cfg:
        srcHost = host["host"]

        for srcD in host["dirs"]:
            srcDir = srcD["src"]

            # Sync each source to each of its dests
            for dstD in srcD["dests"]:
                dstHost = dstD["host"]
                dstDir = dstD["dest"]



                # First mirror host
                if (len(mirrorMap) == 1 and len(mirrorMap[0]) == 0):
                    mirrorHosts.append(dstHost)
                else:
                    #if mirrorHosts[uniqDsts] != dstHost:
                    if dstHost not in mirrorHosts: # If not in list, add it
                        mirrorHosts.append(dstHost)
                        mirrorMap.append([])
                        #print("FINDDDD", mirrorHosts.index(dstHost))

                mirrorId = mirrorHosts.index(dstHost)


                mirrorMap[mirrorId].append([srcHost, srcDir, dstHost, dstDir])

    return mirrorMap

def printFileMap(mirrorMap, showId: bool = True):
    """
        Helper function for printing file mapping
    """
    for i in range(len(mirrorMap)):
        if showId:
            print(i, mirrorMap[i][0][2] + " paths:")
        else:
            print(mirrorMap[i][0][2] + " paths:")
        for j in range(len(mirrorMap[i])):
            srcHost, srcDir = mirrorMap[i][j][0], mirrorMap[i][j][1]
            dstHost, dstDir = mirrorMap[i][j][2], mirrorMap[i][j][3]
            if showId:
                print("\t" + str(i) + "-" + str(j), srcHost, srcDir, dstHost, dstDir)
            else:
                print("\t" + srcHost, srcDir, dstHost, dstDir)

def InteractiveMode(mirrorMap):
    """
        interactive user mode, can mirror, delete, or just sync individual paths
    """
    # TODO: --no-confirm for interactive mode?

    while True:
        # Output list for --interactive mode to choose from
        print("File map to choose from:")
        printFileMap(mirrorMap)

        # Gets selection ID from user
        hostId = -1
        pathId = -1
        selectAll = False
        while pathId < 0 or hostId < 0:
            try:
                selId = input("Input id (or 'q' to quit): ")
                if selId == "q":
                    return
        
                # If the user just picks a host, sync all
                if selId.find("-") == -1:
                    hostId = int(selId)
                    selectAll = True
                    break

                hostId = int(selId[0:selId.find("-")])
                pathId = int(selId[selId.find("-")+1:])

                if hostId > len(mirrorMap) - 1:
                    hostId = -1
                else:
                    if pathId > len(mirrorMap[hostId])-1:
                        pathId = -1

            except KeyboardInterrupt:
                print("\nGoodbye :(")
                sys.exit(0)
            except:
                pass

        # Sync just that selection

        pathAr = []
        if selectAll:
            for i in range(len(mirrorMap[hostId])):
                pathAr.append(i)
        else:
            pathAr.append(pathId)

        ans = ""
        while ans != "d":
            if selectAll:
                print("Paths selected:")
            else:
                print("Path selected:")
            for i in pathAr:
                srcHost = mirrorMap[hostId][i][0]
                srcDir  = mirrorMap[hostId][i][1]
                dstHost = mirrorMap[hostId][i][2]
                dstDir  = mirrorMap[hostId][i][3]
                print(srcHost, srcDir, dstHost, dstDir)

            ans = askUser("What do you want to do?\n\
\n's'ync - sync source files to remote\
\n'r'emote sync - sync remote files to source\
\n'c'lean - remove files on remote that no longer exist on source\
\n't'idy - remove files on source that no longer exist on remote\
\n'd'one - Finished with this dir\
\n\nChoice: ", ["c", "s", "d", "r", "t"])

            # Loops through each path selected (or just one)
            for i in pathAr:
                srcHost = mirrorMap[hostId][i][0]
                srcDir  = mirrorMap[hostId][i][1]
                dstHost = mirrorMap[hostId][i][2]
                dstDir  = mirrorMap[hostId][i][3]

                if ans == "c":
                    SafeRemove(srcHost, srcDir, dstHost, dstDir)
                elif ans == "t":
                    SafeRemove(dstHost, dstDir, srcHost, srcDir)
                elif ans == "s":
                    SafeSync(srcHost, srcDir, dstHost, dstDir)
                elif ans == "r":
                    SafeSync(dstHost, dstDir, srcHost, srcDir)
                elif ans == "d":
                    pass
                else:
                    raise Exception("Invalid response from user!")

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
                elif args.tidy:
                    SafeRemove(dstHost, dstDir, srcHost, srcDir)
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

    parser.add_argument('--tidy', dest='tidy', action='store_const',
                                const=True, default=False,
                                help='Delete files on source not on remote (after sync, unless also --no-sync)')

    parser.add_argument('--map', dest='map', action='store',
                                default="filesMap.json",
                                help='Files to sync together (Default: filesMap.json)')

    args = parser.parse_args()

    # Arg validation

    if args.interactive and (args.mirror or args.delete or args.tidy or not args.sync):
        raise Exception("Cannot use --interactive with --mirror, --delete, --tidy, or --no-sync")

    if args.mirror and (args.delete or args.tidy):
        raise Exception("Cannot --delete or --tidy with --mirror together")

    if args.delete and args.tidy:
        raise Exception("Cannot --delete and --tidy together")

    #if not args.sync and not args.mirror and not args.delete:
    #    raise Exception("So do nothing?")

    return args

if __name__ == "__main__":
    args = parseArgs()

    # JSON File path map
    mirrorMap = readFileMap(args.map)

    if args.interactive:
        InteractiveMode(mirrorMap)
    else:
        # Loop over each hosts mirror Array
        for i in range(len(mirrorMap)):
            AutoMode(mirrorMap[i], args)

