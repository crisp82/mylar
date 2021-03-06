#  This file is part of Mylar.
#
#  Mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mylar is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mylar.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import os
import shutil
import re
import shlex
import time
import logging
import mylar
import subprocess
import urllib2
import sqlite3
from xml.dom.minidom import parseString


from mylar import logger, db, helpers, updater, notifiers, filechecker

class PostProcessor(object):
    """
    A class which will process a media file according to the post processing settings in the config.
    """

    EXISTS_LARGER = 1
    EXISTS_SAME = 2
    EXISTS_SMALLER = 3
    DOESNT_EXIST = 4

#    IGNORED_FILESTRINGS = [ "" ]

    NZB_NAME = 1
    FOLDER_NAME = 2
    FILE_NAME = 3

    def __init__(self, nzb_name, nzb_folder):
        """
        Creates a new post processor with the given file path and optionally an NZB name.

        file_path: The path to the file to be processed
        nzb_name: The name of the NZB which resulted in this file being downloaded (optional)
        """
        # absolute path to the folder that is being processed
        #self.folder_path = ek.ek(os.path.dirname, ek.ek(os.path.abspath, file_path))

        # full path to file
        #self.file_path = file_path

        # file name only
        #self.file_name = ek.ek(os.path.basename, file_path)

        # the name of the folder only
        #self.folder_name = ek.ek(os.path.basename, self.folder_path)

        # name of the NZB that resulted in this folder
        self.nzb_name = nzb_name
        self.nzb_folder = nzb_folder
        #self.in_history = False
        #self.release_group = None
        #self.is_proper = False

        self.log = ''

    def _log(self, message, level=logger.MESSAGE):
        """
        A wrapper for the internal logger which also keeps track of messages and saves them to a string for $

        message: The string to log (unicode)
        level: The log level to use (optional)
        """
#        logger.log(message, level)
        self.log += message + '\n'

    def _run_pre_scripts(self, nzb_name, nzb_folder, seriesmetadata):
        """
        Executes any pre scripts defined in the config.

        ep_obj: The object to use when calling the pre script
        """
        self._log("initiating pre script detection.", logger.DEBUG)
        self._log("mylar.PRE_SCRIPTS : " + mylar.PRE_SCRIPTS, logger.DEBUG)
#        for currentScriptName in mylar.PRE_SCRIPTS:
        currentScriptName = str(mylar.PRE_SCRIPTS).decode("string_escape")
        self._log("pre script detected...enabling: " + str(currentScriptName), logger.DEBUG)
            # generate a safe command line string to execute the script and provide all the parameters
        script_cmd = shlex.split(currentScriptName, posix=False) + [str(nzb_name), str(nzb_folder), str(seriesmetadata)]
        self._log("cmd to be executed: " + str(script_cmd), logger.DEBUG)

            # use subprocess to run the command and capture output
        self._log(u"Executing command "+str(script_cmd))
        self._log(u"Absolute path to script: "+script_cmd[0], logger.DEBUG)
        try:
            p = subprocess.Popen(script_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=mylar.PROG_DIR)
            out, err = p.communicate() #@UnusedVariable
            self._log(u"Script result: "+str(out), logger.DEBUG)
        except OSError, e:
           self._log(u"Unable to run pre_script: " + str(script_cmd))

    def _run_extra_scripts(self, nzb_name, nzb_folder, filen, folderp, seriesmetadata):
        """
        Executes any extra scripts defined in the config.

        ep_obj: The object to use when calling the extra script
        """
        self._log("initiating extra script detection.", logger.DEBUG)
        self._log("mylar.EXTRA_SCRIPTS : " + mylar.EXTRA_SCRIPTS, logger.DEBUG)
#        for curScriptName in mylar.EXTRA_SCRIPTS:
        curScriptName = str(mylar.EXTRA_SCRIPTS).decode("string_escape")
        self._log("extra script detected...enabling: " + str(curScriptName), logger.DEBUG)
            # generate a safe command line string to execute the script and provide all the parameters
        script_cmd = shlex.split(curScriptName) + [str(nzb_name), str(nzb_folder), str(filen), str(folderp), str(seriesmetadata)]
        self._log("cmd to be executed: " + str(script_cmd), logger.DEBUG)

            # use subprocess to run the command and capture output
        self._log(u"Executing command "+str(script_cmd))
        self._log(u"Absolute path to script: "+script_cmd[0], logger.DEBUG)
        try:
            p = subprocess.Popen(script_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=mylar.PROG_DIR)
            out, err = p.communicate() #@UnusedVariable
            self._log(u"Script result: "+str(out), logger.DEBUG)
        except OSError, e:
            self._log(u"Unable to run extra_script: " + str(script_cmd))


    def Process(self):
            self._log("nzb name: " + str(self.nzb_name), logger.DEBUG)
            self._log("nzb folder: " + str(self.nzb_folder), logger.DEBUG)
            logger.fdebug("nzb name: " + str(self.nzb_name))
            logger.fdebug("nzb folder: " + str(self.nzb_folder))
            if mylar.USE_SABNZBD==0:
                logger.fdebug("Not using SABNzbd")
            else:
                # if the SAB Directory option is enabled, let's use that folder name and append the jobname.
                if mylar.SAB_DIRECTORY is not None and mylar.SAB_DIRECTORY is not 'None' and len(mylar.SAB_DIRECTORY) > 4:
                    self.nzb_folder = os.path.join(mylar.SAB_DIRECTORY, self.nzb_name).encode(mylar.SYS_ENCODING)
    
                #lookup nzb_name in nzblog table to get issueid
    
                #query SAB to find out if Replace Spaces enabled / not as well as Replace Decimals
                #http://localhost:8080/sabnzbd/api?mode=set_config&section=misc&keyword=dirscan_speed&value=5
                querysab = str(mylar.SAB_HOST) + "/api?mode=get_config&section=misc&output=xml&apikey=" + str(mylar.SAB_APIKEY)
                #logger.info("querysab_string:" + str(querysab))
                file = urllib2.urlopen(querysab)
                data = file.read()
                file.close()
                dom = parseString(data)

                try:
                    sabreps = dom.getElementsByTagName('replace_spaces')[0].firstChild.wholeText
                except:
                    errorm = dom.getElementsByTagName('error')[0].firstChild.wholeText
                    logger.error(u"Error detected attempting to retrieve SAB data : " + errorm)
                    return
                sabrepd = dom.getElementsByTagName('replace_dots')[0].firstChild.wholeText
                logger.fdebug("SAB Replace Spaces: " + str(sabreps))
                logger.fdebug("SAB Replace Dots: " + str(sabrepd))
            if mylar.USE_NZBGET==1:
                logger.fdebug("Using NZBGET")
                logger.fdebug("NZB name as passed from NZBGet: " + self.nzb_name)
            myDB = db.DBConnection()

            if self.nzb_name == 'Manual Run':
                print ("manual run initiated")
                #Manual postprocessing on a folder.
                #use the nzb_folder to determine every file
                #walk the dir,
                #once a series name and issue are matched,
                #write the series/issue/filename to a tuple
                #when all done, iterate over the tuple until completion...
                comicseries = myDB.action("SELECT * FROM comics")
                manual_list = []
                if comicseries is None: 
                    logger.error(u"No Series in Watchlist - aborting Manual Post Processing. Maybe you should be running Import?")
                    return
                else:
                    ccnt=0
                    nm=0
                    watchvals = {}
                    for cs in comicseries:
                        watchvals = {"SeriesYear":   cs['ComicYear'],
                                     "Total":        cs['Total']}
                        watchmatch = filechecker.listFiles(self.nzb_folder,cs['ComicName'],cs['AlternateSearch'], manual=watchvals)
                        if watchmatch is None:
                            nm+=1
                            pass
                        else:
                            fn = 0
                            fccnt = int(watchmatch['comiccount'])
                            if len(watchmatch) == 1: continue
                            while (fn < fccnt):
                                try:
                                    tmpfc = watchmatch['comiclist'][fn]
                                except IndexError,KeyError:
                                    break
                                temploc= tmpfc['JusttheDigits'].replace('_', ' ')
                                temploc = re.sub('[\#\']', '', temploc)
                                logger.fdebug("temploc: " + str(temploc))

                                ww = shlex.split(temploc)
                                lnw = len(ww)
                                wdc = 0
                                while (wdc < lnw):
                                    #counts get buggered up when the issue is the last field in the filename - ie. '50.cbr'
                                    if ".cbr" in ww[wdc].lower():
                                        ww[wdc] = ww[wdc].replace(".cbr", "")
                                    elif ".cbz" in ww[wdc].lower():
                                        ww[wdc] = ww[wdc].replace(".cbz", "")
                                    if "(c2c)" in ww[wdc].lower():
                                        ww[wdc] = ww[wdc].replace("(c2c)", " ")
                                        get_issue = shlex.split(str(ww[wdc]))
                                        if ww[wdc] != " ":
                                            ww[wdc] = get_issue[0]

                                    if '.' in ww[wdc]:
                                    #logger.fdebug("decimal detected...adjusting.")
                                        try:
                                            i = float(ww[wdc])
                                        except ValueError, TypeError:
                                        #not numeric
                                        #logger.fdebug("NOT NUMERIC - new word: " + str(ww[wdc]))
                                            ww[wdc] = ww[wdc].replace(".", "")
                                    else:
                                        #numeric
                                        pass

                                    if ww[wdc].isdigit():
                                        if int(ww[wdc]) > 0:
                                            if wdc+1 < len(ww) and 'au' in ww[wdc+1].lower():
                                                if len(ww[wdc+1]) == 2:
                                                #if the 'AU' is in 005AU vs 005 AU it will yield different results.
                                                    ww[wdc] = ww[wdc] + 'AU'
                                                    ww[wdc+1] = '93939999919190933'
                                                    logger.info("AU Detected seperate from issue - combining and continuing")

                                    fcdigit = helpers.issuedigits(ww[wdc])
                                    if 'annual' in self.nzb_name.lower():
                                        logger.info("annual detected.")
                                        annchk = "yes"
                                        issuechk = myDB.action("SELECT * from annuals WHERE ComicID=? AND Int_IssueNumber=?", [cs['ComicID'],fcdigit]).fetchone()
                                    else:
                                        issuechk = myDB.action("SELECT * from issues WHERE ComicID=? AND Int_IssueNumber=?", [cs['ComicID'],fcdigit]).fetchone()

                                    if issuechk is None:
                                        logger.info("No corresponding issue # found for " + str(cs['ComicID']))
                                    else:
                                        logger.info("Found matching issue # " + str(fcdigit) + " for ComicID: " + str(cs['ComicID']) + " / IssueID: " + str(issuechk['IssueID']))
                                        manual_list.append({"ComicLocation":   tmpfc['ComicLocation'],
                                                            "ComicID":         cs['ComicID'],
                                                            "IssueID":         issuechk['IssueID'],
                                                            "IssueNumber":     issuechk['Issue_Number'],
                                                            "ComicName":       cs['ComicName']})
                                        ccnt+=1
                                        print manual_list
                                    wdc+=1
                                fn+=1
                    print("There are " + str(len(manual_list)) + " files found that match on your watchlist, " + str(nm) + " do not match anything and will be ignored.")    
                

            else:
                nzbname = self.nzb_name
                #remove extensions from nzb_name if they somehow got through (Experimental most likely)
                extensions = ('.cbr', '.cbz')

                if nzbname.lower().endswith(extensions):
                    fd, ext = os.path.splitext(nzbname)
                    self._log("Removed extension from nzb: " + ext, logger.DEBUG)
                    nzbname = re.sub(str(ext), '', str(nzbname))

                #replace spaces
                nzbname = re.sub(' ', '.', str(nzbname))
                nzbname = re.sub('[\,\:\?]', '', str(nzbname))
                nzbname = re.sub('[\&]', 'and', str(nzbname))

                logger.fdebug("After conversions, nzbname is : " + str(nzbname))
#                if mylar.USE_NZBGET==1:
#                    nzbname=self.nzb_name
                self._log("nzbname: " + str(nzbname), logger.DEBUG)
   
                nzbiss = myDB.action("SELECT * from nzblog WHERE nzbname=?", [nzbname]).fetchone()

                if nzbiss is None:
                    self._log("Failure - could not initially locate nzbfile in my database to rename.", logger.DEBUG)
                    logger.fdebug("Failure - could not locate nzbfile initially.")
                    # if failed on spaces, change it all to decimals and try again.
                    nzbname = re.sub('_', '.', str(nzbname))
                    self._log("trying again with this nzbname: " + str(nzbname), logger.DEBUG)
                    logger.fdebug("trying again with nzbname of : " + str(nzbname))
                    nzbiss = myDB.action("SELECT * from nzblog WHERE nzbname=?", [nzbname]).fetchone()
                    if nzbiss is None:
                        logger.error(u"Unable to locate downloaded file to rename. PostProcessing aborted.")
                        return
                    else:
                        self._log("I corrected and found the nzb as : " + str(nzbname))
                        logger.fdebug("auto-corrected and found the nzb as : " + str(nzbname))
                        issueid = nzbiss['IssueID']
                else: 
                    issueid = nzbiss['IssueID']
                    logger.fdebug("issueid:" + str(issueid))
                    sarc = nzbiss['SARC']
                    #use issueid to get publisher, series, year, issue number

                annchk = "no"
                if 'annual' in nzbname.lower():
                    logger.info("annual detected.")
                    annchk = "yes"
                    issuenzb = myDB.action("SELECT * from annuals WHERE IssueID=? AND ComicName NOT NULL", [issueid]).fetchone()
                else:
                    issuenzb = myDB.action("SELECT * from issues WHERE IssueID=? AND ComicName NOT NULL", [issueid]).fetchone()

                if issuenzb is not None:
                    logger.info("issuenzb found.")
                    if helpers.is_number(issueid):
                        sandwich = int(issuenzb['IssueID'])
                else:
                    logger.info("issuenzb not found.")
                    #if it's non-numeric, it contains a 'G' at the beginning indicating it's a multi-volume
                    #using GCD data. Set sandwich to 1 so it will bypass and continue post-processing.
                    if 'S' in issueid:
                        sandwich = issueid
                    elif 'G' in issueid or '-' in issueid: 
                        sandwich = 1
                if helpers.is_number(sandwich):
                    if sandwich < 900000:
                        # if sandwich is less than 900000 it's a normal watchlist download. Bypass.
                        pass
                else:
                    if issuenzb is None or 'S' in sandwich or int(sandwich) >= 900000:
                        # this has no issueID, therefore it's a one-off or a manual post-proc.
                        # At this point, let's just drop it into the Comic Location folder and forget about it..
                        if 'S' in sandwich:
                            self._log("One-off STORYARC mode enabled for Post-Processing for " + str(sarc))
                            logger.info("One-off STORYARC mode enabled for Post-Processing for " + str(sarc))
                            if mylar.STORYARCDIR:
                                storyarcd = os.path.join(mylar.DESTINATION_DIR, "StoryArcs", sarc)
                                self._log("StoryArc Directory set to : " + storyarcd, logger.DEBUG)
                            else:
                                self._log("Grab-Bag Directory set to : " + mylar.GRABBAG_DIR, logger.DEBUG)
   
                        else:
                            self._log("One-off mode enabled for Post-Processing. All I'm doing is moving the file untouched into the Grab-bag directory.", logger.DEBUG)
                            logger.info("One-off mode enabled for Post-Processing. Will move into Grab-bag directory.")
                            self._log("Grab-Bag Directory set to : " + mylar.GRABBAG_DIR, logger.DEBUG)

                        for root, dirnames, filenames in os.walk(self.nzb_folder):
                            for filename in filenames:
                                if filename.lower().endswith(extensions):
                                    ofilename = filename
                                    path, ext = os.path.splitext(ofilename)
      
                        if 'S' in sandwich:
                            if mylar.STORYARCDIR:
                                grdst = storyarcd
                            else:
                                grdst = mylar.DESTINATION_DIR
                        else:
                            if mylar.GRABBAG_DIR:
                                grdst = mylar.GRABBAG_DIR
                            else:
                                grdst = mylar.DESTINATION_DIR
   
                        filechecker.validateAndCreateDirectory(grdst, True)
    
                        if 'S' in sandwich:
                            #if from a StoryArc, check to see if we're appending the ReadingOrder to the filename
                            if mylar.READ2FILENAME:
                                issuearcid = re.sub('S', '', issueid)
                                arcdata = myDB.action("SELECT * FROM readinglist WHERE IssueARCID=?",[issuearcid]).fetchone()
                                if int(arcdata['ReadingOrder']) < 10: readord = "00" + str(arcdata['ReadingOrder'])
                                elif int(arcdata['ReadingOrder']) > 10 and int(arcdata['ReadingOrder']) < 99: readord = "0" + str(arcdata['ReadingOrder'])
                                else: readord = str(arcdata['ReadingOrder'])
                                dfilename = str(readord) + "-" + ofilename
                            else:
                                dfilename = ofilename
                            grab_dst = os.path.join(grdst, dfilename)
                        else:
                            grab_dst = os.path.join(grdst, ofilename)

                        self._log("Destination Path : " + grab_dst, logger.DEBUG)
                        logger.info("Destination Path : " + grab_dst)
                        grab_src = os.path.join(self.nzb_folder, ofilename)
                        self._log("Source Path : " + grab_src, logger.DEBUG)
                        logger.info("Source Path : " + grab_src)

                        logger.info("Moving " + str(ofilename) + " into directory : " + str(grdst))

                        try:
                            shutil.move(grab_src, grab_dst)
                        except (OSError, IOError):
                            self._log("Failed to move directory - check directories and manually re-run.", logger.DEBUG)
                            logger.debug("Failed to move directory - check directories and manually re-run.")
                            return
                        #tidyup old path
                        try:
                            shutil.rmtree(self.nzb_folder)
                        except (OSError, IOError):
                            self._log("Failed to remove temporary directory.", logger.DEBUG)
                            logger.debug("Failed to remove temporary directory - check directory and manually re-run.")
                            return

                        logger.debug("Removed temporary directory : " + str(self.nzb_folder))
                        self._log("Removed temporary directory : " + self.nzb_folder, logger.DEBUG)
                        #delete entry from nzblog table
                        myDB.action('DELETE from nzblog WHERE issueid=?', [issueid])

                        if 'S' in issueid:
                            issuearcid = re.sub('S', '', issueid)
                            logger.info("IssueArcID is : " + str(issuearcid))
                            ctrlVal = {"IssueArcID":  issuearcid}
                            newVal = {"Status":    "Downloaded",
                                      "Location":  grab_dst }
                            myDB.upsert("readinglist",newVal,ctrlVal)
                            logger.info("updated status to Downloaded")
                        return self.log


            if self.nzb_name == 'Manual Run':
                #loop through the hits here.
                if len(manual_list) == '0':
                    logger.info("No hits ... breakout.")
                    return

                for ml in manual_list:
                    comicid = ml['ComicID']
                    issueid = ml['IssueID']
                    issuenumOG = ml['IssueNumber']
                    self.Process_next(comicid,issueid,issuenumOG,ml)
                return
            else:
                comicid = issuenzb['ComicID']
                issuenumOG = issuenzb['Issue_Number']
                return self.Process_next(comicid,issueid,issuenumOG)

    def Process_next(self,comicid,issueid,issuenumOG,ml=None):
            annchk = "no"
            extensions = ('.cbr', '.cbz')
            myDB = db.DBConnection()
            comicnzb = myDB.action("SELECT * from comics WHERE comicid=?", [comicid]).fetchone()
            issuenzb = myDB.action("SELECT * from issues WHERE issueid=? AND comicid=? AND ComicName NOT NULL", [issueid,comicid]).fetchone()
            print "issueid: " + str(issueid)
            print "issuenumOG: " + str(issuenumOG)
            if issuenzb is None:
                print "chk1"
                issuenzb = myDB.action("SELECT * from annuals WHERE issueid=? and comicid=?", [issueid,comicid]).fetchone()
                print "chk2"
                annchk = "yes"
            print issuenzb
            #issueno = str(issuenum).split('.')[0]
            #new CV API - removed all decimals...here we go AGAIN!
            issuenum = issuenzb['Issue_Number']
            issue_except = 'None'
            if 'au' in issuenum.lower():
                issuenum = re.sub("[^0-9]", "", issuenum)
                issue_except = ' AU'
            elif 'ai' in issuenum.lower():
                issuenum = re.sub("[^0-9]", "", issuenum)
                issue_except = ' AI'
            if '.' in issuenum:
                iss_find = issuenum.find('.')
                iss_b4dec = issuenum[:iss_find]
                iss_decval = issuenum[iss_find+1:]
                if int(iss_decval) == 0:
                    iss = iss_b4dec
                    issdec = int(iss_decval)
                    issueno = str(iss)
                    self._log("Issue Number: " + str(issueno), logger.DEBUG)
                    logger.fdebug("Issue Number: " + str(issueno))
                else:
                    if len(iss_decval) == 1:
                        iss = iss_b4dec + "." + iss_decval
                        issdec = int(iss_decval) * 10
                    else:
                        iss = iss_b4dec + "." + iss_decval.rstrip('0')
                        issdec = int(iss_decval.rstrip('0')) * 10
                    issueno = iss_b4dec
                    self._log("Issue Number: " + str(iss), logger.DEBUG)
                    logger.fdebug("Issue Number: " + str(iss))
            else:
                iss = issuenum
                issueno = str(iss)
            # issue zero-suppression here
            if mylar.ZERO_LEVEL == "0": 
                zeroadd = ""
            else:
                if mylar.ZERO_LEVEL_N  == "none": zeroadd = ""
                elif mylar.ZERO_LEVEL_N == "0x": zeroadd = "0"
                elif mylar.ZERO_LEVEL_N == "00x": zeroadd = "00"

            logger.fdebug("Zero Suppression set to : " + str(mylar.ZERO_LEVEL_N))

            if str(len(issueno)) > 1:
                if int(issueno) < 10:
                    self._log("issue detected less than 10", logger.DEBUG)
                    if '.' in iss:
                        if int(iss_decval) > 0:
                            issueno = str(iss)
                            prettycomiss = str(zeroadd) + str(iss)
                        else:
                            prettycomiss = str(zeroadd) + str(int(issueno))
                    else:
                        prettycomiss = str(zeroadd) + str(iss)
                    if issue_except != 'None': 
                        prettycomiss = str(prettycomiss) + issue_except
                    self._log("Zero level supplement set to " + str(mylar.ZERO_LEVEL_N) + ". Issue will be set as : " + str(prettycomiss), logger.DEBUG)
                elif int(issueno) >= 10 and int(issueno) < 100:
                    self._log("issue detected greater than 10, but less than 100", logger.DEBUG)
                    if mylar.ZERO_LEVEL_N == "none":
                        zeroadd = ""
                    else:
                        zeroadd = "0"
                    if '.' in iss:
                        if int(iss_decval) > 0:
                            issueno = str(iss)
                            prettycomiss = str(zeroadd) + str(iss)
                        else:
                           prettycomiss = str(zeroadd) + str(int(issueno))
                    else:
                        prettycomiss = str(zeroadd) + str(iss)
                    if issue_except != 'None':
                        prettycomiss = str(prettycomiss) + issue_except
                    self._log("Zero level supplement set to " + str(mylar.ZERO_LEVEL_N) + ".Issue will be set as : " + str(prettycomiss), logger.DEBUG)
                else:
                    self._log("issue detected greater than 100", logger.DEBUG)
                    if '.' in iss:
                        if int(iss_decval) > 0:
                            issueno = str(iss)
                    prettycomiss = str(issueno)
                    if issue_except != 'None':
                        prettycomiss = str(prettycomiss) + issue_except
                    self._log("Zero level supplement set to " + str(mylar.ZERO_LEVEL_N) + ". Issue will be set as : " + str(prettycomiss), logger.DEBUG)
            else:
                prettycomiss = str(issueno)
                self._log("issue length error - cannot determine length. Defaulting to None:  " + str(prettycomiss), logger.DEBUG)

            if annchk == "yes":
                prettycomiss = "Annual " + str(prettycomiss)
                self._log("Annual detected.")
            logger.fdebug("Pretty Comic Issue is : " + str(prettycomiss))
            issueyear = issuenzb['IssueDate'][:4]
            self._log("Issue Year: " + str(issueyear), logger.DEBUG)
            logger.fdebug("Issue Year : " + str(issueyear))
#            comicnzb= myDB.action("SELECT * from comics WHERE comicid=?", [comicid]).fetchone()
            publisher = comicnzb['ComicPublisher']
            self._log("Publisher: " + publisher, logger.DEBUG)
            logger.fdebug("Publisher: " + str(publisher))
            #we need to un-unicode this to make sure we can write the filenames properly for spec.chars
            series = comicnzb['ComicName'].encode('ascii', 'ignore').strip()
            self._log("Series: " + series, logger.DEBUG)
            logger.fdebug("Series: " + str(series))
            seriesyear = comicnzb['ComicYear']
            self._log("Year: " + seriesyear, logger.DEBUG)
            logger.fdebug("Year: "  + str(seriesyear))
            comlocation = comicnzb['ComicLocation']
            self._log("Comic Location: " + comlocation, logger.DEBUG)
            logger.fdebug("Comic Location: " + str(comlocation))
            comversion = comicnzb['ComicVersion']
            self._log("Comic Version: " + str(comversion), logger.DEBUG)
            logger.fdebug("Comic Version: " + str(comversion))
            if comversion is None:
                comversion = 'None'
            #if comversion is None, remove it so it doesn't populate with 'None'
            if comversion == 'None':
                chunk_f_f = re.sub('\$VolumeN','',mylar.FILE_FORMAT)
                chunk_f = re.compile(r'\s+')
                chunk_file_format = chunk_f.sub(' ', chunk_f_f)
                self._log("No version # found for series - tag will not be available for renaming.", logger.DEBUG)
                logger.fdebug("No version # found for series, removing from filename")
                logger.fdebug("new format is now: " + str(chunk_file_format))
            else:
                chunk_file_format = mylar.FILE_FORMAT

            ofilename = None

            #tag the meta.
            if mylar.ENABLE_META:
                self._log("Metatagging enabled - proceeding...")
                logger.fdebug("Metatagging enabled - proceeding...")
                pcheck = "pass"
                try:
                    import cmtagmylar
                    if ml is None:
                        pcheck = cmtagmylar.run(self.nzb_folder, issueid=issueid)
                    else:
                        pcheck = cmtagmylar.run(self.nzb_folder, issueid=issueid, manual="yes", filename=ml['ComicLocation'])

                except ImportError:
                    logger.fdebug("comictaggerlib not found on system. Ensure the ENTIRE lib directory is located within mylar/lib/comictaggerlib/")
                    logger.fdebug("continuing with PostProcessing, but I'm not using metadata.")
                    pcheck = "fail"
                
                if pcheck == "fail":
                    self._log("Unable to write metadata successfully - check mylar.log file. Attempting to continue without tagging...")
                    logger.fdebug("Unable to write metadata successfully - check mylar.log file. Attempting to continue without tagging...")
                elif pcheck == "unrar error":
                    self._log("This is a corrupt archive - whether CRC errors or it's incomplete. Marking as BAD, and retrying a different copy.")
                    logger.error("This is a corrupt archive - whether CRC errors or it's incomplete. Marking as BAD, and retrying a different copy.")
                    return self.log
                else:
                    otofilename = pcheck
                    self._log("Sucessfully wrote metadata to .cbz - Continuing..")
                    logger.fdebug("Sucessfully wrote metadata to .cbz (" + str(otofilename) + ") - Continuing..")
            #Run Pre-script

            if mylar.ENABLE_PRE_SCRIPTS:
                nzbn = self.nzb_name #original nzb name
                nzbf = self.nzb_folder #original nzb folder
                #name, comicyear, comicid , issueid, issueyear, issue, publisher
                #create the dic and send it.
                seriesmeta = []
                seriesmetadata = {}
                seriesmeta.append({
                            'name':                 series,
                            'comicyear':            seriesyear,
                            'comicid':              comicid,
                            'issueid':              issueid,
                            'issueyear':            issueyear,
                            'issue':                issuenum,
                            'publisher':            publisher
                            })
                seriesmetadata['seriesmeta'] = seriesmeta
                self._run_pre_scripts(nzbn, nzbf, seriesmetadata )

        #rename file and move to new path
        #nfilename = series + " " + issueno + " (" + seriesyear + ")"

            file_values = {'$Series':    series,
                           '$Issue':     prettycomiss,
                           '$Year':      issueyear,
                           '$series':    series.lower(),
                           '$Publisher': publisher,
                           '$publisher': publisher.lower(),
                           '$VolumeY':   'V' + str(seriesyear),
                           '$VolumeN':   comversion
                          }


            #if it's a Manual Run, use the ml['ComicLocation'] for the exact filename.
            if ml is None:

                for root, dirnames, filenames in os.walk(self.nzb_folder):
                    for filename in filenames:
                        if filename.lower().endswith(extensions):
                            ofilename = filename
                            path, ext = os.path.splitext(ofilename)
            else:
                print "otofilename:" + str(otofilename)
                odir, ofilename = os.path.split(otofilename)
                print "ofilename: " + str(ofilename)
                path, ext = os.path.splitext(ofilename)
                print "path: " + str(path)
                print "ext:" + str(ext)

            if ofilename is None:
                logger.error(u"Aborting PostProcessing - the filename doesn't exist in the location given. Make sure that " + str(self.nzb_folder) + " exists and is the correct location.")
                return
            self._log("Original Filename: " + ofilename, logger.DEBUG)
            self._log("Original Extension: " + ext, logger.DEBUG)
            logger.fdebug("Original Filname: " + str(ofilename))
            logger.fdebug("Original Extension: " + str(ext))

            if mylar.FILE_FORMAT == '' or not mylar.RENAME_FILES:
                self._log("Rename Files isn't enabled...keeping original filename.", logger.DEBUG)
                logger.fdebug("Rename Files isn't enabled - keeping original filename.")
                #check if extension is in nzb_name - will screw up otherwise
                if ofilename.lower().endswith(extensions):
                    nfilename = ofilename[:-4]
                else:
                    nfilename = ofilename
            else:
                nfilename = helpers.replace_all(chunk_file_format, file_values)
                if mylar.REPLACE_SPACES:
                    #mylar.REPLACE_CHAR ...determines what to replace spaces with underscore or dot
                    nfilename = nfilename.replace(' ', mylar.REPLACE_CHAR)
            nfilename = re.sub('[\,\:\?]', '', nfilename)
            self._log("New Filename: " + nfilename, logger.DEBUG)
            logger.fdebug("New Filename: " + str(nfilename))

            src = os.path.join(self.nzb_folder, ofilename)

            filechecker.validateAndCreateDirectory(comlocation, True)

            if mylar.LOWERCASE_FILENAMES:
                dst = (comlocation + "/" + nfilename + ext).lower()
            else:
                dst = comlocation + "/" + nfilename + ext.lower()    
            self._log("Source:" + src, logger.DEBUG)
            self._log("Destination:" +  dst, logger.DEBUG)
            logger.fdebug("Source: " + str(src))
            logger.fdebug("Destination: " + str(dst))

            if ml is None:
                #non-manual run moving/deleting...
                os.rename(os.path.join(self.nzb_folder, str(ofilename)), os.path.join(self.nzb_folder,str(nfilename + ext)))
                src = os.path.join(self.nzb_folder, str(nfilename + ext))
                try:
                    shutil.move(src, dst)
                except (OSError, IOError):
                    self._log("Failed to move directory - check directories and manually re-run.", logger.DEBUG)
                    self._log("Post-Processing ABORTED.", logger.DEBUG)
                    return
                #tidyup old path
                try:
                    shutil.rmtree(self.nzb_folder)
                except (OSError, IOError):
                    self._log("Failed to remove temporary directory - check directory and manually re-run.", logger.DEBUG)
                    self._log("Post-Processing ABORTED.", logger.DEBUG)
                    return

                self._log("Removed temporary directory : " + str(self.nzb_folder), logger.DEBUG)
            else:
                #Manual Run, this is the portion.
                logger.fdebug("Renaming " + os.path.join(self.nzb_folder, str(ofilename)) + " ..to.. " + os.path.join(self.nzb_folder,str(nfilename + ext)))
                os.rename(os.path.join(self.nzb_folder, str(ofilename)), os.path.join(self.nzb_folder,str(nfilename + ext)))
                src = os.path.join(self.nzb_folder, str(nfilename + ext))
                logger.fdebug("Moving " + src + " ... to ... " + dst)
                try:
                    shutil.move(src, dst)
                except (OSError, IOError):
                    logger.fdebug("Failed to move directory - check directories and manually re-run.")
                    logger.fdebug("Post-Processing ABORTED.")
                    return
                logger.fdebug("Successfully moved to : " + dst)
                #tidyup old path
                #try:
                #    os.remove(os.path.join(self.nzb_folder, str(ofilename)))
                #    logger.fdebug("Deleting : " + os.path.join(self.nzb_folder, str(ofilename)))
                #except (OSError, IOError):
                #    logger.fdebug("Failed to remove temporary directory - check directory and manually re-run.")
                #    logger.fdebug("Post-Processing ABORTED.")
                #    return
                #logger.fdebug("Removed temporary directory : " + str(self.nzb_folder))

                    #delete entry from nzblog table
            myDB.action('DELETE from nzblog WHERE issueid=?', [issueid])
                    #update snatched table to change status to Downloaded
            if annchk == "no":
                updater.foundsearch(comicid, issueid, down='True')
            else:
                updater.foundsearch(comicid, issueid, mode='want_ann', down='True')
                    #force rescan of files
            updater.forceRescan(comicid)
            logger.info(u"Post-Processing completed for: " + series + " issue: " + str(issuenumOG) )
            self._log(u"Post Processing SUCCESSFULL! ", logger.DEBUG)
            if ml is not None: 
                return
            else:
                if mylar.PROWL_ENABLED:
                    pushmessage = series + '(' + issueyear + ') - issue #' + issuenumOG
                    logger.info(u"Prowl request")
                    prowl = notifiers.PROWL()
                    prowl.notify(pushmessage,"Download and Postprocessing completed")
    
                if mylar.NMA_ENABLED:
                    nma = notifiers.NMA()
                    nma.notify(series, str(issueyear), str(issuenumOG))

                if mylar.PUSHOVER_ENABLED:
                    pushmessage = series + ' (' + str(issueyear) + ') - issue #' + str(issuenumOG)
                    logger.info(u"Pushover request")
                    pushover = notifiers.PUSHOVER()
                    pushover.notify(pushmessage, "Download and Post-Processing completed")
             
            # retrieve/create the corresponding comic objects

            if mylar.ENABLE_EXTRA_SCRIPTS:
                folderp = str(dst) #folder location after move/rename
                nzbn = self.nzb_name #original nzb name
                filen = str(nfilename + ext) #new filename
                #name, comicyear, comicid , issueid, issueyear, issue, publisher
                #create the dic and send it.
                seriesmeta = []
                seriesmetadata = {}
                seriesmeta.append({
                            'name':                 series,
                            'comicyear':            seriesyear,
                            'comicid':              comicid,
                            'issueid':              issueid,
                            'issueyear':            issueyear,
                            'issue':                issuenum,
                            'publisher':            publisher
                            })
                seriesmetadata['seriesmeta'] = seriesmeta
                self._run_extra_scripts(nzbname, self.nzb_folder, filen, folderp, seriesmetadata )

            return self.log

