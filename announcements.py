#===============================================================================
# This file creates the cog which controls the announcements the bot makes
# for weekly and special quests
#
# Since this program requires both accessing the database and interacting
# with members/the server, it was easier to make it it's own file than
# to split it between Member_interactions and DB_interactions. Therefore,
# this program handles any queries to the announcement tables in the database
# and any messages which involve announcing quests for members
#===============================================================================

# basic discord and Sqlite libraries
import discord
from discord.ext import commands, tasks
import sqlite3
# used to handle the announcement/end dates and the announcement cycle
import datetime
import asyncio
# used for image handling
import os.path
# used for the logger
import logging

# announcement database contents:
# -- eventAnnounce:
# ---- quest number, announcement date, end date
# -- weeklyAnnounce:
# ---- quest number, announcement date

class announceSystem(commands.Cog):
    """Handles any announcements regarding the quest system,
    automatically sending any in the database to the discord server
    and pinging those that are opt in to the announcements
    """
    def __init__(self, bot, db_path):
        """Initializes the cog.
        Stores the parent bot and the path to the database.
        Also tests the database path to ensure it exists
        """
        self._bot = bot
        self._logger = logging.getLogger('bot activity')
        self._dbpath = db_path
        try:
            test = sqlite3.connect(db_path)
            test.close()
        except Exception as e:
            print(e)
            self._logger.critical("announcements:init:Connection Error: %s", str(e))
            
        self.announcementTimer.start()
        
    @commands.Cog.listener()
    async def on_connect(self):
        """Creates the connection to the database and a cursor
        for use in the methods once the bot connects to discord's servers.
        """
        self._connection = sqlite3.connect(self._dbpath)
        self._cursor = self._connection.cursor()
        self._google = self._bot.get_cog("google_interact")
            
    @commands.Cog.listener()
    async def on_ready(self):
        """Gathers references to the server, the channel the bot will make
        announcements in, and the role to mention in announcements.
        This method also starts the timer for the announcement cycle
        """
        guildref = self._bot.get_guild(236626664304410634)
        self._channelRef = guildref.get_channel(386773986991931392)
        self._rolesref = {}
        with open("./references/roles.txt", "r") as file:
            file.readline()
            roleList = file.read().split("\n")
            for item in roleList:
                item = item.split(" - ")
                if item != ['']:
                    self._rolesref[item[0]] = guildref.get_role(int(item[1]))
        
    async def addAnnouncements(self, announcements):
        """Takes a list of announcements from the quest system spreadsheet,
        gathered in the Google_interactions cog, then inserts each item into
        the database
        """
        for item in announcements:
            try:
                if not await self.questExists(int(item[1])):
                    self._logger.warning("announcements:addAnnouncements:Quit Warning: couldn't add item %s due to nonexistance", item[1])
                    continue
                elif len(item) == 4 and item[3].lower() == "remove":
                    await self.removeAnnouncement(item)
                    del item
                    continue
                
                announceTime = datetime.datetime.strptime(item[2], "%m/%d/%Y").date() # convert the date from a string to a datetime object
                if item[0] == "event": # if this is an event quest, check if there is a defined end date
                    if len(item) > 3: # if there is, convert it to a datetime
                        endTime = datetime.datetime.strptime(item[3], "%m/%d/%Y").date()
                    else: # if not, specify there is none
                        endTime = "N/A"
                    self._cursor.execute("INSERT INTO eventAnnounce VALUES (?,?,?)", (int(item[1]), announceTime, endTime))
                elif item[0] == "weekly": # If it is a weekly quest, simply add it to the database
                    self._cursor.execute("INSERT INTO weeklyAnnounce VALUES (?, ?)", (int(item[1]), announceTime))
            
            except Exception as e:
                self._logger.error("announcements:addAnnouncements:Insertion Error: %s", str(e))
            
        self._logger.info("announcements:addAnnouncements: added %s new announcements\n%s", str(len(announcements)), str(announcements))
        self._connection.commit()
        
    async def questExists(self, questNum):
        """Searches the quests table in the database to ensure
        the given quest exists. Used when loading announcements into the
        database
        """
        # Find the quest
        try:
            quest = self._cursor.execute("SELECT * FROM quests WHERE number=?", (questNum,))
        except Exception as e:
            print(e)
            self._logger.error("announcements:questExists:Selection Error: %s", str(e))
            return False
        
        # Test if the quest has any associated values
        if quest == []:
            self._logger.info("announcements:questExists: Tested quest number %s for existance, returned False", str(questNum))
            return False
        else:
            self._logger.info("announcements:questExists: Tested quest number %s for existance, returned True", str(questNum))
            return True
        
    async def removeAnnouncement(self, announce):
        """Removes an announcement from the database
        based on their quest number and announcement date.
        
        Since this method is designed to work with the addAnnouncements method,
        it does not commit the change at the end, rather it allows addAnnouncements to
        do so after it makes all the changes requested from the spreadsheet
        """
        announceDate = datetime.datetime.strptime(announce[2], "%m/%d/%Y").date() # Get the datetime of the announcement date
        try:
            if announce[0] == "event": # Remove from event table
                self._cursor.execute("DELETE FROM eventAnnounce WHERE number=? AND announceDate=?", (announce[1], announceDate))
            elif announce[0] == "weekly": # Remove from weekly table
                self._cursor.execute("DELETE FROM weeklyAnnounce WHERE number=? AND announceDate=?", (announce[1], announceDate))
        
        except Exception as e:
            self._logger.error("announcements:removeAnnouncement:Deletion Error: %s", str(e))
            return
        else:
            self._logger.info("announcements:removeAnnouncement: removed quest %s on date %s from %s", str(announce[1]), announce[2], announce[0])
        
    async def weekly_announce(self):
        """Checks the weeklyAnnounce table of the database
        for any quest that needs to be announced. If there is,
        it sends a message to the announcement channel with a mention
        for quest members and each quest that needs to be announced
        """
        date = datetime.date.today() # Used to find today's announcements
        # If today's date does not fall on the date for weekly announcements,
        # automatically quit
        if date.strftime("%A") != "Friday":
            return
        nextDate = date + datetime.timedelta(days=7)
        nextDateString = nextDate.strftime("%b. %d") # Used when making the announcement
        ranks = ("F", "E", "D", "C", "B", "A", "S", "S+", "Unranked") # Used for searching for a quest poster
        
        try:
            # Select every announcement that matches today's date
            announces = self._cursor.execute("SELECT * FROM weeklyAnnounce WHERE announceDate=?", (date,)).fetchall()
        
            if announces != [] : # If announcements are found, mention quest members
                await self._channelRef.send(f"{self._rolesref['F'].mention} {self._rolesref['E'].mention} {self._rolesref['D'].mention} {self._rolesref['C'].mention}"
                                          + f"{self._rolesref['B'].mention} {self._rolesref['A'].mention} {self._rolesref['S'].mention} {self._rolesref['S+'].mention}"
                                           + "\n\nHere are the weekly quests for this week!")
            
            for item in announces: # for each announcment
                # Find the quest in the database and check if a poster is saved to the server
                quest = self._cursor.execute("SELECT * FROM quests WHERE number=?", (item[0],)).fetchall()[0]
                imagePath = f"./questPics/{ranks[quest[3]]}/quest{quest[0]}.jpg"
                if os.path.exists(imagePath): # If there is a poster, create an embed to send to the server
                    announcement = discord.Embed(title=f"{quest[0]} - {quest[1]}", description=f"Ends on {nextDateString}",
                                                 colour=discord.Colour.dark_red(), type="image")
                    with open(imagePath, 'rb') as image:
                        attachment = discord.File(image, filename="image0.jpg")
                        announcement.set_image(url=f"attachment://image0.jpg")
                        
                    await self._channelRef.send(embed=announcement, file=attachment)
                else: # If there is no poster, create a text announcement to send instead
                    firstline = f"*{quest[6]}*"
                    if quest[3] >= 0:
                        firstline = firstline + f" - Rank **{ranks[quest[3]]}**"
                    announcement =  discord.Embed(title=f"{quest[0]} - {quest[1]}", description=firstline,
                                                 colour=discord.Colour.dark_red())
                    announcement.add_field(name=f"{quest[2]}", value=f"Rewards: {quest[4]} Experience, {quest[5]} gold\n"
                                    + f"Ends on {nextDateString}")
                    
                    await self._channelRef.send(embed=announcement)
                
        except Exception as e:
            self._logger.error("announcements:weekly_announce:Selection Error: %s", str(e))
        else: # If no error occured, delete every announcement from today or earlier
            self._logger.info("announcements:weekly_announce: gathered %s items from table weeklyAnnounce\n%s", str(len(announces)), str(announces))
            self._cursor.execute("DELETE FROM weeklyAnnounce WHERE announceDate<=?;", (date,))
            self._logger.info("announcements:weekly_announce: deleted items from table weeklyAnnounce with date <= %s", str(date))
            self._connection.commit()
        
    async def event_announce(self):
        """Checks the eventAnnounce table in the database for special quests
        to be announced. If there are, it sends a message to the server
        with a mention for quest system members and the quests
        
        This works basically the same as the weekly_announce method
        """
        date = datetime.date.today()
        nextDay = date + datetime.timedelta(days=1) # Used for quests with no given end date, assuming it is a one day event
        nextDayString = nextDay.strftime("%b. %d")
        ranks = ("F", "E", "D", "C", "B", "A", "S", "S+", "Unranked")
        
        try:
            announces = self._cursor.execute("SELECT * FROM eventAnnounce WHERE announceDate=?", (date,)).fetchall()
        
            if announces != [] :
                await self._channelRef.send(f"{self._rolesref['F'].mention} {self._rolesref['E'].mention} {self._rolesref['D'].mention} {self._rolesref['C'].mention}"
                                          + f"{self._rolesref['B'].mention} {self._rolesref['A'].mention} {self._rolesref['S'].mention} {self._rolesref['S+'].mention}"
                                            + "\n\nThere are some special quests for today, check them out!")
            
            for item in announces:
                quest = self._cursor.execute("SELECT * FROM quests WHERE number=?", (item[0],)).fetchall()[0]
                imagePath = f"./questPics/{ranks[quest[3]]}/quest{quest[0]}.jpg"
                if os.path.exists(imagePath):
                    if item[2] == "N/A": # If there is no given end date, set the end date to tommorow
                        endString = nextDayString
                    else: # Otherwise, convert the end date to a readable string
                        endString = datetime.datetime.strptime(item[2],
                            "%Y-%m-%d").strftime("%b. %d")
                    # Create the embed
                    announcement = discord.Embed(title=f"{quest[0]} - {quest[1]}", description=f"Ends on {endString}",
                                                 colour=discord.Colour.dark_red(), type="image")
                    with open(imagePath, 'rb') as image:
                        attachment = discord.File(image, filename="image0.jpg")
                        announcement.set_image(url=f"attachment://image0.jpg")
                        
                    await self._channelRef.send(embed=announcement, file=attachment)
                else:
                    if item[2] == "N/A":
                        endString = nextDayString
                    else:
                        endString = datetime.datetime.strptime(item[2],
                                                  "%Y-%m-%d").strftime("%b. %d")
                    firstline = f"*{quest[6]}*"
                    if quest[3] >= 0:
                        firstline = firstline + f" - Rank **{ranks[quest[3]]}**"
                    announcement =  discord.Embed(title=f"{quest[0]} - {quest[1]}", description=firstline,
                                                 colour=discord.Colour.dark_red(), type="image")
                    announcement.add_field(name=f"{quest[2]}", value=f"Rewards: {quest[4]} Experience, {quest[5]} gold\n"
                                    + f"Ends on {endString}")
                
                    await self._channelRef.send(embed=announcement)
                
        except Exception as e:
            self._logger.error("announcements:event_announce:Selection Error: %s", str(e))
        else:
            self._logger.info("announcements:event_announce: gathered %s items from table eventAnnounce\n%s", str(len(announces)), str(announces))
            self._cursor.execute("DELETE FROM eventAnnounce WHERE announceDate<=?;", (date,))
            self._logger.info("announcements:event_announce: deleted items from table eventAnnounce with date <= %s", str(date))
            self._connection.commit()
    
    async def runAnnouncements(self):
        """Runs all announcement methods in the cog, then automatically
        sets a timer to rerun the method at a given time the next day
        """
        self._logger.info("announcements:runAnnouncements: running announcement cycle")
        await self.weekly_announce()
        await self.event_announce()
        await self._google.updateSpreadsheet()
        self._logger.info("announcements:runAnnouncements: announcement cycle complete")
        
    @tasks.loop(seconds=5.0)
    async def announcementTimer(self):
        """The primary method which controls when the bot
        checks for and makes announcements
        """
        now = datetime.datetime.now() # right now
        nextTime = datetime.datetime.combine(datetime.datetime.today(), datetime.time(hour=8)) # a datetime representing the next target cycle time
        if nextTime < now: # if the nextTime object is behind right now
            nextTime = nextTime + datetime.timedelta(days=1) # push it up by 1 day
        
        difference = nextTime - now # take the time difference between right now and the next target cycle
        self._logger.info("announcements:announcementTimer: Time set to next update cycle: %s to %s", str(difference), str(nextTime))
        await asyncio.sleep(difference.total_seconds()) # Set a timer for the next update
        
        await self.runAnnouncements() # run the announcements and loop
        
    @announcementTimer.before_loop
    async def before_timer(self):
        print('announcements is waiting...')
        await self._bot.wait_until_ready()
        print('announcements is ready!')
    
    async def get_all(self):
        """Returns all quests currently in the announcement
        tables in the database. Used to update the spreadsheet
        """
        quests = []
        
        try:
            weekly = self._cursor.execute("SELECT * FROM weeklyAnnounce").fetchall()
            event = self._cursor.execute("SELECT * FROM eventAnnounce").fetchall()
        except Exception as e:
            self._logger.error("announcements:get_all:Selection Error: %s", str(e))
            return("error")
        else:
            self._logger.info("announcements:get_all: gathered %s items from weeklyAnnounce\n%s", str(len(weekly)), str(weekly))
            self._logger.info("announcements:get_all: gathered %s items from eventAnnounce\n%s", str(len(event)), str(event))
            quests.append(weekly)
            quests.append(event)
            return(quests)
            
    async def retrieve_quests(self):
        """Retrieves any quests that are currently running.
        This is not currently used for anything, and is not complete
        """
        date = datetime.date.today()
        
        #gets currently running event/weekly quests and returns them
