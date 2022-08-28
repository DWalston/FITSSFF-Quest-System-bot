#===============================================================================
# This file creates the cog which makes requests using the Google APIs
# to manage the committee spreadsheets and completed quest submissions.
#
# This cog also executes automatic updates for both the spreadsheets and the database
#===============================================================================

# imports used for the google API,
# Which for some reason is a lot
from __future__ import print_function
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# Basic Discord tools
import discord
from discord.ext import commands, tasks
# Used to handle dates when uploading and downloading
import datetime
import dateparser
# Used to handle the update cycle loop
import asyncio
import logging

class google_interact(commands.Cog):
    """Handles any bot action which involves
    using the google API
    """
    def __init__(self, bot):
        """Initializes the cog.
        Stores the parent bot and calls
        the method which sets up the google
        API tools
        """
        self._bot = bot
        self._logger = logging.getLogger('bot activity')
        self.setupAPI()
        
        self.updateTimer.start()
        
    @commands.Cog.listener()
    async def on_connect(self):
        """Gathers references to the announcements
        and DB_interactions cogs when the bot connects to
        discord's servers
        """
        self._announce = self._bot.get_cog("announceSystem")
        self._db = self._bot.get_cog("db_interact")
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Gathers a reference to the server"""
        self._guildRef = self._bot.get_guild(236626664304410634)
        
    def setupAPI(self):
        """Sets up the tools necessary for the google API.
        This was mostly taken from the google API docs,
        so it would be best to reference those for additional information
        """
        creds = None
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        try:
            if os.path.exists('token.json'):
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            # If there are no (valid) credentials available, let the user log in.
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
        except Exception as e:
            self._logger.critical("Google_interactions:setupAPI:Setup Error: %s", str(e))
        
        # Create the services necessary for the actions the bot makes,
        # and store the IDs for the quest spreadsheets
        self._sheetService = build("sheets", "v4", credentials=creds)
        self._driveService = build("drive", "v3", credentials=creds)
        self._spreadsheetID = ("1cst4m3t9BXADFpFbqZYmK7MPCaFrZ3Pq0Qz_sHxA0kw",
                               "1AtJ4sc7DvVHpuU0YWaWUVyPe0vB2gOKVPlOfraT8_Sc",
                               "1Es7IgyfmyJDxZ53aBZ_Sjqlw2-r3bv03rUhjnT3dT0M")
        
    async def updateSelf(self):
        """Updates the database using info from the
        master spreadsheet. This includes member info
        and completed quests.
        """
        # updating the approved completed quests, and deleting the rejected completions
        range_ = "Pending Quests submits!A3:L"
        
        try:
            result = self._sheetService.spreadsheets().values().get(
                        spreadsheetId=self._spreadsheetID[0], range=range_).execute()
        except Exception as e:
            self._logger.error("Google_interactions:updateSelf:Get Error: %s in master %s", str(e), range_)
            return
                
        rows = result.get("values", [])
        self._logger.info("Google_interactions:updateSelf: gathered %s items from master %s\n%s", str(len(rows)), range_, str(rows))
        unreviewed = [] # Used to track items which need to be returned
        
        for row in rows: # for each item
            if len(row) == 10: # If the row does not have an item in the "approved" column
                unreviewed.append(row) # Add to unreviewed items
            elif row[10].upper() == "SUBMISSION ERROR": # If it was previously returned because of an error
                unreviewed.append(row) # Return it to the spreadsheet
            elif row[10].upper() == "YES": # If it was approved
                complete = await self._db.questSubmit(int(row[0]), int(row[3]), row[9]) # Try to add it to the user's log
                if not complete: # If it did not add,
                    # return it to the spreadsheet
                    row[10] = "SUBMISSION ERROR"
                    unreviewed.append(row)
            # If it was rejected, it is simply ignored

        try:
            # Clear the old submissions
            errorType = "Clear"
            self._sheetService.spreadsheets().values().clear(
                spreadsheetId=self._spreadsheetID[0], range=range_).execute()
            self._logger.info("Google_interactions:updateSelf: cleared all items from master %s", range_)
            if unreviewed != []: # if there are items to be returned
                # Send the items back to the spreadsheet
                body = {"values":unreviewed}
                valueInput="RAW"
                errorType = "Update"
                self._sheetService.spreadsheets().values().update(
                    spreadsheetId=self._spreadsheetID[0], range=range_,
                    valueInputOption=valueInput, body=body).execute()
                self._logger.info("Google_interactions:updateSelf: added %s items to %s\n%s", str(len(unreviewed)), range_, str(unreviewed))
        except Exception as e:
            self._logger.error("Google_interactions:updateSelf:%s Error: %s in master %s", errorType, str(e), range_)
            return
            
        # updating the member database
        range_ = "Members!A:P"
        
        # Grab the items from the spreadsheet
        try:
            result = self._sheetService.spreadsheets().values().get(
                    spreadsheetId=self._spreadsheetID[0], range=range_).execute()
        except Exception as e:
            self._logger.error("Google_interactions:updateSelf:Get Error: %s in master %s", str(e), range_)
            return
                
        rows = result.get("values", [])
        self._logger.info("Google_interactions:updateSelf: gathered %s items from master %s\n%s", str(len(rows)), range_, str(rows))
        
        if rows[0][1].upper() == "YES": # If there were edits put into the sheet
            # Reset the edited field to "NO"
            try:
                self._sheetService.spreadsheets().values().update(
                    spreadsheetId=self._spreadsheetID[0], range="Members!B1:B1",
                    valueInputOption="RAW", body={"values" : [["NO"]]}).execute()
            except Exception as e:
                self._logger.error("Google_interactions:updateSelf:Update Error: %s in master Members!B1:B1", str(e))
                return
            else:
                self._logger.info("Google_interactions:updateSelf: set master Members!B1:B1 to 'NO'")
                
            for row in rows[2:]: # For each member
                # Get the member's info from discord
                memberId = int(row[0])
                member = self._guildRef.get_member(memberId)
                if len(row) == 16: # If there are items in the edits column
                    editField = row[15] # Grab the edits
                    if editField.lower() == "remove": # If they are being removed, send to delete method
                        await self._db.deleteMember(memberId)
                    else:
                        # Split the edits by commas, add a change to update the member's discord name,
                        # then send the request to the database
                        editField = editField.split(",")
                        editField.append("discordname:'" + member.name + "#" + member.discriminator)
                        await self._db.editMemberItems(memberId, editField)
                        # Check to ensure the level of the member did not become outdated
                        await self._db.checkMemberLevel(memberId)
                else: # If no edits were made to the item
                    # Update the member's discord name, then
                    # Check the member's level and rank
                    editField = ["discordname:'" + member.name + "#" + member.discriminator,]
                    await self._db.editMemberItems(memberId, editField)
                    await self._db.checkMemberLevel(memberId)
            
            # Clear the old edits
            range_ = "Members!P3:P"
            try:
                self._sheetService.spreadsheets().values().clear(
                    spreadsheetId=self._spreadsheetID[0], range=range_).execute()
            except Exception as e:
                self._logger.error("Google_interactions:updateSelf:Clear Error: %s in master %s", str(e), range_)
                return
            else:
                self._logger.info("Google_interactions:updateSelf: cleared all items from master %s", range_)

        else: # If no edits were made,
            # Update each member's discord name in the database
            for row in rows[2:]:
                memberId = int(row[0])
                member = self._guildRef.get_member(memberId)
                editField = ["discordname:'" + member.name + "#" + member.discriminator,]
                await self._db.editMemberItems(memberId, editField)
                
    async def updateQuests(self):
        """Updates the assorted items which are related to
        quests, such as loading the quest list into the database
        and taking quest submissions to put into the master sheet
        """
        # collect quests and put into database
        ranks = {"F":0, "E":1, "D":2, "C":3, "B":4, "A":5, "S":6, "S+":7}
        quests = []
        # Repeatable Quests
        range_ = "Repeatable!A2:G"
        questType = "repeatable"
        try:
            result = self._sheetService.spreadsheets().values().get(
                spreadsheetId=self._spreadsheetID[1], range=range_).execute()
        except Exception as e:
            self._logger.error("Google_interactions:updateQuests:Get Error: %s in quests %s", str(e), range_)
            return
        
        rows = result.get("values", [])
        self._logger.info("Google_interactions:updateQuests: Gathered %s items from quests %s\n%s", str(len(rows)), range_, str(rows))
        for row in rows:
            if len(row) >= 6:
                desc = row[2] + " - " + row[5]
                rank = -1
                if len(row) > 6:
                    if "Rank " in row[6]:
                        rank = row[6][row[6].find("Rank ") + 5] # Find the letter after Rank
                        rank = ranks[rank] # Convert the letter to the given number
                
                quests.append((row[0], row[1], desc, rank, row[3], row[4], questType))
        
        # Ranked Quests
        ranges = ("F Rank!A2:G", "E Rank!A2:G", "D Rank!A2:G",
                  "C Rank!A2:G", "B Rank!A2:G", "A Rank!A2:G",
                  "S Rank!A2:G", "S+ Rank!A2:G")
        
        for i in range(len(ranges)):
            range_ = ranges[i]
            rank = i
            try:
                result = self._sheetService.spreadsheets().values().get(
                    spreadsheetId=self._spreadsheetID[1], range=range_).execute()
            except Exception as e:
                self._logger.error("Google_interactions:updateQuests:Get Error: %s in quests %s", str(e), range_)
                return
                
            rows = result.get("values", [])
            self._logger.info("Google_interactions:updateQuests: Gathered %s items from quests %s\n%s", str(len(rows)), range_, str(rows))
            for row in rows:
                if len(row) >= 6:
                    desc = row[2] + " - " + row[5]
                    questType = "ranked"
                    if len(row) > 6:
                        if "Heroic" in row[6]:
                            questType = "heroic"
                
                    quests.append((row[0], row[1], desc, rank, row[3], row[4], questType))
                
        # Special Quests
        range_ = "Event Specific!A2:F"
        try:
            result = self._sheetService.spreadsheets().values().get(
                spreadsheetId=self._spreadsheetID[1], range=range_).execute()
        except Exception as e:
            self._logger.error("Google_interactions:updateQuests:Get Error: %s in quests %s", str(e), range_)
            return
        
        rows = result.get("values", [])
        self._logger.info("Google_interactions:updateQuests: Gathered %s items from quests %s\n%s", str(len(rows)), range_, str(rows))
        for row in rows:
            if len(row) >= 6:
                desc = row[2] + " - " + row[5]
                rank = -1
                questType = "special"
                if len(row) > 6:
                    if "Rank " in row[6]:
                        rank = row[6][row[6].find("Rank ") + 5] # Find the letter after Rank
                        rank = ranks[rank] # Convert the letter to the given number
                    if "Heroic" in row[6]:
                        questType = questType + " - heroic"
                    if "Repeatable" in row[6]:
                        questType = questType + " - repeatable"
                
                quests.append((row[0], row[1], desc, rank, row[3], row[4], questType))
        
        # Send all the quests to the database
        complete = await self._db.loadQuests(quests)
        if not complete:
            self._logger.critical("Google_interactions:updateQuests:Error: Could not upload quests to database\n%s", str(quests))
        
        # collect the quest images
        # driveIDs are the ids for each folder that has posters,
        # and ranks are the rank of the quest each ID has
        driveIDs = ('1eqncAKw4-ruaBviZuSNGw-k9QIFM__l_', '1u4hDaq9BH8JURrQsUeLgshIHNLJXYQyI',
                    '1nIpzZUEYTaX8bRe_f_7LcLHnEdIzKZ8s', '1JQ09XQ9UIyBKI21J-QmLpTehXF7L6IR7',
                    '1II9tzExIzQmbE25Do3q8ieib81C56nxK', '1pha0nkvdDGxvRu_2YZT9q3zMbxrx1X6d',
                    '1xLsYmdKHTkRkqg0ptGSZmMtl4mmcqV_1', '16Nl2f5GepUOQgpK73dk4yNVxjWZpXxRP')
        ranks = ('F', 'E', 'D', 'C', 'B', 'A', 'S', 'S+')
        
        for i in range(len(driveIDs)): # for each folder
            # grab the ID and rank
            ID = driveIDs[i]
            rank = ranks[i]
            #logging
            query = f"'{ID}' in parents and mimeType='image/jpeg'"
            files = []
            
            page_token=None
            while True:
                try:
                    response = self._driveService.files().list(q=query,
                                                           spaces='drive',
                                                           fields='nextPageToken, '
                                                           'files(id, name)',
                                                           pageToken=page_token).execute()
                except Exception as e:
                    print(e)
                    #logging
                    return
                
                files.extend(response.get('files', []))
                page_token = response.get('nextPageToken', None)
                if page_token is None:
                    break
                
            self._logger.info("Google_interactions:updateQuests: found %s total items in drive %s\n%s", str(len(files)), rank, str(files))
            for file in files:
                fileName = file.get("name")
                fileID = file.get("id")
                if not os.path.exists(f"./questPics/{rank}/{fileName}"):
                    self._logger.info("Google_interactions:updateQuests: new file found; downloading image %s - ID %s", fileName, fileID)
                    try:
                        request = self._driveService.files().get_media(fileId=fileID)
                    
                        with open(f"./questPics/{rank}/{fileName}", "wb") as file:
                            downloader = MediaIoBaseDownload(file, request)
                            done = False
                            while not done:
                                status, done = downloader.next_chunk()
                                self._logger.info("Google_interactions:updateQuests: Download %s", str(int(status.progress() * 100)))
                            
                    except Exception as e:
                        self._logger.error("Google_interactions:updateQuests:Downloader Error: %s for file %s in drive %s", str(e), fileName, rank)
                    else:
                        self._logger.info("Google_interactions:updateQuests: file downloaded under questPics\\%s\\%s", rank, fileName)
        
        # updating the announcements
        range_ = "Quests to announce!A2:D"
        try:
            result = self._sheetService.spreadsheets().values().get(
                    spreadsheetId=self._spreadsheetID[0], range=range_).execute()
        except Exception as e:
            self._logger.error("Google_interactions:updateQuests:Get Error: %s in master %s", str(e), range_)
            return
        
        rows = result.get("values", [])    
        self._logger.info("Google_interactions:updateQuests: gathered %s items from master %s\n%s", str(len(rows)), range_, str(rows))
        if rows != []:
            await self._announce.addAnnouncements(rows)
            
        # clear old announcements
        try:
            self._sheetService.spreadsheets().values().clear(
                    spreadsheetId=self._spreadsheetID[0], range=range_).execute()
        except Exception as e:
            self._logger.error("Google_interactions:updateQuests:Clear Error: %s in master %s", str(e), range_)
            return
        else:
            self._logger.info("Google_interactions:updateQuests: cleared all items from master %s", range_)
        
        # collect submissions and put into the approval spreadsheet
        range_ = "Form Responses 1!A2:R"
        questlist = [] # quests that can be added
        failedQuests = [] # quests with submission errors
        try:
            file = self._sheetService.spreadsheets().values().get(
                spreadsheetId=self._spreadsheetID[2], range=range_).execute()
            
            submissions = file.get("values", [])
            self._logger.info("Google_interactions:updateQuests: gathered %s items from submissions %s\n%s", len(submissions), range_, str(submissions))
        except Exception as e:
            self._logger.error("Google_interactions:updateQuests:Get Error: %s in submissions %s", str(e), range_)
            return
        
        for submit in submissions:
            if len(submit) < 18:
                continue
            quest = []
            # Search for the member based on their discord name
            # If not found return the submission and quit
            memInfo = await self._db.fetchMemberName(submit[17])
            if memInfo == "error" or memInfo == "none found":
                self._logger.warning("Google_interactions:updateQuests:Quit Warning: Member %s could not be found for quest submission", submit[17])
                failedQuests.append(submit)
                continue
            quest.append(str(memInfo[0])) # Member ID
            quest.append(submit[1]) # Member Name
            quest.append(submit[2].lower()) # Quest Type
            
            # The data layout for each quest type is different.
            # Each if statement has the data collection for a given type
            if quest[2] == "repeatable":
                questInfo = await self._db.fetchQuest(submit[12]) # get the quest info
                # If not found, return submission and quit
                if questInfo == "error" or questInfo == "none found":
                    self._logger.warning("Google_interactions:updateQuests:Quit Warning: Quest %s could not be found for quest submission", submit[12])
                    failedQuests.append(submit)
                    continue
                quest.append(questInfo[0]) # quest number
                quest.append(questInfo[1]) # quest name
                for i in range(4): # empty data columns
                    quest.append('')
            elif quest[2] == "ranked":
                questInfo = await self._db.fetchQuest(submit[8])
                if questInfo == "error" or questInfo == "none found":
                    self._logger.warning("Google_interactions:updateQuests:Quit Warning: Quest %s could not be found for quest submission", submit[8])
                    failedQuests.append(submit)
                    continue
                quest.append(questInfo[0]) # Quest Number
                quest.append(questInfo[1]) # Quest Name
                quest.append('') # Empty column
                quest.append(submit[9]) # Quest Committee witnesses
                quest.append(submit[10]) # Other witnesses
                quest.append(submit[11]) # additional proof
            elif quest[2] == "heroic":
                questInfo = await self._db.fetchQuest(submit[3])
                if questInfo == "error" or questInfo == "none found":
                    self._logger.warning("Google_interactions:updateQuests:Quit Warning: Quest %s could not be found for quest submission", submit[3])
                    failedQuests.append(submit)
                    continue
                quest.append(questInfo[0]) # quest Number
                quest.append(questInfo[1]) # quest name
                quest.append(submit[4]) # other participants
                quest.append(submit[5]) # Quest Committee witnesses
                quest.append(submit[6]) # other witnesses
                quest.append(submit[7]) # additional proof
            else: # Special quests
                questInfo = await self._db.fetchQuest(submit[13])
                if questInfo == "error" or questInfo == "none found":
                    self._logger.warning("Google_interactions:updateQuests:Quit Warning: Quest %s could not be found for quest submission", submit[13])
                    failedQuests.append(submit)
                    continue
                quest.append(questInfo[0]) # Quest Number
                quest.append(questInfo[1]) # Quest Name
                quest.append('') # Empty column
                quest.append(submit[14]) # Quest Committee witnesses
                quest.append(submit[16]) # Other witnesses
                quest.append(submit[15]) # additional proof
                
            quest.append(dateparser.parse(submit[0]).date().strftime("%m/%d/%Y")) # add the date submitted
            questlist.append(quest) # add to the return list
            
        if questlist != []: # if at least one quest was successfully parsed
            # add them to the pending quest submissions sheet in the master spreadsheet
            range_="Pending Quests submits!A3:J"
            values = {"values":questlist}
            
            try:
                result = self._sheetService.spreadsheets().values().append(
                    spreadsheetId=self._spreadsheetID[0], range=range_,
                    valueInputOption="RAW", body=values).execute()
            except Exception as e:
                self._logger.error("Google_interactions:updateQuests:Append Error: %s in master %s", str(e), range_)
                return
            else:
                self._logger.info("Google_interactions:updateQuests: added %s items to master %s\n%s", str(len(questlist)), range_, str(questlist))
        
        # Clear the added submissions and return the failed parsed quests
        range_ = "Form Responses 1!A2:R"
        try:
            self._sheetService.spreadsheets().values().clear(
                spreadsheetId=self._spreadsheetID[2], range=range_).execute()
        except Exception as e:
            self._logger.error("Google_interactions:updateQuests:Clear Error: %s in submissions %s", str(e), range_)
            return
        else:
            self._logger.info("Google_interactions:updateQuests: cleared all items in submissions %s", range_)
            
        if failedQuests != []: # If at least one failed
            # Record the amount of failed submissions
            # to add to the pending quest submissions sheet
            failed = len(failedQuests)
            values = {"values":failedQuests}
            try:
                sheet = "master" # for logging purposes
                self._sheetService.spreadsheets().values().update(
                    spreadsheetId=self._spreadsheetID[2], range=range_,
                    valueInputOption="RAW", body=values).execute()
                self._logger.info("Google_interactions:updateQuests: added %s items to submissions %s\n%s", str(len(failedQuests)), range_, str(failedQuests))
                    
                range_ = "Pending Quests submits!M1:M1" # for logging purposes
                sheet = "submissions"
                self._sheetService.spreadsheets().values().update(
                    spreadsheetId=self._spreadsheetID[0], range=range_,
                    valueInputOption="RAW", body={"values":[[str(failed)]]}).execute()
                self._logger.info("Google_interactions:updateQuests: set submissions %s to value %s", range_, str(failed))
            except Exception as e:
                self._logger.error("Google_interactions:updateQuests:Update Error: %s in %s %s", str(e), sheet, range_)
                return
        
        else: # if no failures, update the value to be 0
            try:
                self._sheetService.spreadsheets().values().update(
                    spreadsheetId=self._spreadsheetID[0], range="Pending Quests submits!M1:M1",
                    valueInputOption="RAW", body={"values":[["0"]]}).execute()
            except Exception as e:
                self._logger.error("Google_interactions:updateQuests:Update Error: %s in submissions Pending Quests submits!M1:M1", str(e))
                return
            else:
                self._logger.info("Google_interactions:updateQuests: set submissions Pending Quests submits!M1:M1 to value 0")
    
    async def updateSpreadsheet(self):
        """Update the master spreadsheet with information from
        the database, which is primarily targeted at the member
        and current pending announcements spreadsheets
        """
        # Update members spreadsheet
        range_ = "Members!A3:O"
        valueInput = "RAW"
        
        # Get all the items in the adventurers table from the database
        values = await self._db.getFromTableFilter("adventurers", order="lastname ASC")
        if values == "error":
            return
        else:
            for i in range(len(values)):
                temp = list(values[i])
                temp[0] = str(temp[0])
                values[i] =  temp
        
        body = {
            "values" : values
            }
        # Remove the old information and send the new data
        try:
            errorType = "Clear"
            self._sheetService.spreadsheets().values().clear(
                spreadsheetId=self._spreadsheetID[0], range=range_).execute()
            self._logger.info("Google_interactions:updateSpreadsheet: cleared all items from master %s", range_)
            
            errorType = "Update"
            self._sheetService.spreadsheets().values().update(
                spreadsheetId=self._spreadsheetID[0], range=range_,
                valueInputOption=valueInput, body=body).execute()
            self._logger.info("Google_interactions:updateSpreadsheet: added %s items to master %s\n%s", str(len(values)), range_, str(values))
        except Exception as e:
            self._logger.error("Google_interactions:updateSpreadsheet:%s Error: %s in master %s", errorType, str(e), range_)
            return
            
        # Update pending announcements
        values = await self._announce.get_all() # get_all returns a 2D nested list
        # Index 0 is weekly quests
        range_ = "Announcement List!A3:B"
        body = {
            "values" : values[0]
            }
        
        try:
            errorType = "Clear"
            self._sheetService.spreadsheets().values().clear(
                    spreadsheetId=self._spreadsheetID[0], range=range_).execute()
            self._logger.info("Google_interactions:updateSpreadsheet: cleared all items from master %s", range_)
                    
            errorType = "Append"
            self._sheetService.spreadsheets().values().append(
                            spreadsheetId=self._spreadsheetID[0], range=range_,
                            valueInputOption=valueInput, body=body).execute()
            self._logger.info("Google_interactions:updateSpreadsheet: added %s items to master %s\n%s", str(len(values[0])), range_, str(values[0]))
        except Exception as e:
            self._logger.error("Google_interactions:updateSpreadsheet:%s Error: %s in master %s", errorType, str(e), range_)
            return
        
        # Index 1 is event quests
        range_ = "Announcement List!D3:F"
        body = {
            "values" : values[1]
            }
        
        try:
            errorType = "Clear"
            self._sheetService.spreadsheets().values().clear(
                    spreadsheetId=self._spreadsheetID[0], range=range_).execute()
            self._logger.info("Google_interactions:updateSpreadsheet: cleared all items from master %s", range_)
                    
            errorType = "Append"
            self._sheetService.spreadsheets().values().append(
                            spreadsheetId=self._spreadsheetID[0], range=range_,
                            valueInputOption=valueInput, body=body).execute()
            self._logger.info("Google_interactions:updateSpreadsheet: added %s items to master %s\n%s", str(len(values[0])), range_, str(values[0]))
        except Exception as e:
            self._logger.error("Google_interactions:updateSpreadsheet:%s Error: %s in master %s", errorType, str(e), range_)
            return
        
    async def uploadSpreadsheet(self, memberId):
        """Uploads a member's quest log to the
        Member Quest Log sheet in the master spreadsheet.
        """
        range_ = "Member Quest Log!A2:C2"
        valueInput = "RAW"
        member = await self._db.fetchMember(memberId)
        if member == "none found" or member == "error":
            self._logger.warning("Google_interactions:uploadSpreadsheet:Quit Warning: member %s could not be found in database", str(memberId))
            return
        
        values = [[str(memberId), member[1], datetime.datetime.today().strftime("%d/%m/%Y")]]
        body = {
            "values" : values
            }
        
        try:
            self._sheetService.spreadsheets().values().update(
                spreadsheetId=self._spreadsheetID[0], range=range_,
                valueInputOption=valueInput, body=body).execute()
        except Exception as e:
            self._logger.error("Google_interactions:uploadSpreadsheet:Update Error: %s in master %s", str(e), range_)
            return False
        else:
            self._logger.info("Google_interactions:uploadSpreadsheet: updated master %s with items %s", range_, str(values))
        
        range_ = "Member Quest Log!A4:G"
        dbname = str(memberId) + "questLog"
        values = await self._db.getFromTableFilter(dbname, order="number ASC")
        body = {
            "values" : values
            }
        
        try:
            errorType = "Clear"
            self._sheetService.spreadsheets().values().clear(
                spreadsheetId=self._spreadsheetID[0], range=range_).execute()
            self._logger.info("Google_interactions:uploadSpreadsheet: cleared all items from master %s", range_)
            
            errorType = "Append"
            self._sheetService.spreadsheets().values().append(
                spreadsheetId=self._spreadsheetID[0], range=range_,
                valueInputOption=valueInput, body=body).execute()
            self._logger.info("Google_interactions:uploadSpreadsheet: added %s items to master %s\n%s", str(len(values)), range_, str(values))
        except Exception as e:
            self._logger.error("Google_interactions:uploadSpreadsheet:%s Error: %s in master %s", errorType, str(e), range_)
            return False
            
        return True
        
    async def runUpdate(self):
        self._logger.info("Google_interactions:runUpdate: running update cycle")
        await self.updateSelf()
        await self.updateQuests()
        await self.updateSpreadsheet()
        self._logger.info("Google_interactions:runUpdate: completed update cycle")
        
    @tasks.loop(seconds=5.0)
    async def updateTimer(self):
        """The primary method which controls when the bot
        checks for and makes announcements
        """
        now = datetime.datetime.now() # right now
        nextTime = datetime.datetime.combine(datetime.datetime.today(), datetime.time(hour=2)) # a datetime representing the next target cycle time
        if nextTime < now: # if the nextTime object is behind right now
            nextTime = nextTime + datetime.timedelta(days=1) # push it up by 1 day
        
        difference = nextTime - now # take the time difference between right now and the next target cycle
        self._logger.info("Google_interactions:updateTimer: Time set to next update cycle: %s to %s", str(difference), str(nextTime))
        await asyncio.sleep(difference.total_seconds()) # Set a timer for the next update
        
        await self.runUpdate() # Run all the updates

    @updateTimer.before_loop
    async def before_timer(self):
        print('update is waiting...')
        await self._bot.wait_until_ready()
        print('update is ready!')
