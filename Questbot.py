#===============================================================================
# This is the main file for FITSSFF's quest system bot.
#
# This program creates and runs the bot, utilizing the cogs made in
# the other files.
#
# Created by:
# David Walston, Spring 2022
#
# Updated by:
#
#===============================================================================

# Basic discord API tools
import discord
from discord.ext import commands
# I'm using the discord_components library to make running
# interactive elements like lists easier. It is a public
# opensource library which extends discord's current API build
# to include components
from discord_components import ComponentsBot, Select, SelectOption
#used for the admin methods
import asyncio
# Python's built in logger library. Most of the libraries used
# for this project are already compatible with this
import logging
# Importing the cogs
from DB_interactions import db_interact
from Member_interactions import memb_interact
from Google_interactions import google_interact
from announcements import announceSystem

# Set up the loggers for the cogs
# Basic logger
handler = logging.FileHandler(filename='./logs/errors.log', encoding='utf-8', mode='w')
logging.basicConfig(handlers=[handler])

# Discord Logger
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='./logs/discord.log', encoding='utf-8', mode='w')
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s :%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Database Logger
logger = logging.getLogger('sqlite3')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='./logs/database.log', encoding='utf-8', mode='w')
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Google API Logger
logger = logging.getLogger('googleapiclient')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='./logs/google.log', encoding='utf-8', mode='w')
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Bot activity Logger
logger = logging.getLogger('bot activity')
logger.propagate = False
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='./logs/botactions.log', encoding='utf-8', mode='w')
formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class admin (commands.Cog):
    """This Cog is used to hold all admin commands for the bot
    It also holds the listeners used to log the bot's connection activity
    """
    def __init__(self, bot):
        """Initializes the Cog. Also stores the parent bot
        and gathers a reference for the Goole_interactions and 
        announcements Cogs, for use in the forceUpdate commands
        """
        self._bot = bot
        self._db = bot.get_cog("db_interact")
        self._updatecog = bot.get_cog("google_interact")
        self._announcecog = bot.get_cog("announceSystem")
        self._logger = logging.getLogger('bot activity')
    
    @commands.Cog.listener()    
    async def on_ready(self):
        """Prints a statement to the standard output to signify the bot
        is ready to operate. Also gathers a reference to the FITSSFF server
        for use in discerning users able to access the admin commands
        """
        print(f"Logged in as {self._bot.user}")
        self._logger.info(f"admin: Logged in as {self._bot.user}, ready to operate")
        self._guildRef = self._bot.get_guild(236626664304410634)
    
    @commands.Cog.listener()
    async def on_connect(self):
        """Prints a statement when the bot has connected to
        Discord's servers. Also logs the event and time
        """
        print("Connected to server")
        self._logger.info("admin: Connected to server")
    
    @commands.Cog.listener()
    async def on_disconnect(self):
        """Prints a statement when the bot disconnects from
        Discord's servers. Also logs the event and time
        NOTE: according to discord's API docs, the reconnection
        methods (i.e. on_resumed) will not be called for every instance
        the on_disconnect listener is called, due to how the logic on
        the connection testing works. This means you will see many
        disconnection logs without a corresponding reconnection call,
        which is by design.
        """
        print("Disconnected, please stand by")
        self._logger.warning("admin: Disconnected from server")
        
    @commands.Cog.listener()
    async def on_resumed(self):
        """Prints a statement when the bot resumes a session,
        which means it successfully reconnected to the discord
        server after a local disconnection (i.e. internet problems)
        """
        print("Reconnected, resume actions")
        self._logger.warning("admin: Reconnected to server")
        
    def has_admin():
        """A test predicate to test if a given individual can use the admin commands.
        In the release version, this will allow anyone with the quest system goblins
        or officer roles to use admin commands. In the test version, this is restricted
        to just the owner of the bot
        """
        def predicate(ctx):
            guildref = ctx.bot.get_guild(236626664304410634)
            memberRoles = ctx.message.author.roles
            return (guildref.get_role(386767668637728781) in memberRoles
                    or guildref.get_role(891117388261621760) in memberRoles)
            #return ctx.bot.is_owner(ctx.message.author)
        return commands.check(predicate)
        
    @commands.command()
    @has_admin()
    async def sayHi(self, ctx):
        """A simple command which replies in the channel the command is given.
        Used to test if the bot is connected and functioning.
        """
        await ctx.send("Hello!")
        
    @commands.command()
    @has_admin()
    async def getInfo(self, ctx):
        """Prints a list of information about the server it is called from.
        Returns the guild name + ID, the channel names + IDS, and
        the roles + IDs. Used to setup the bot
        """
        guild = ctx.guild
        print(guild.name + ", " + str(guild.id))
        print("CHANNELS")
        for channel in guild.channels:
            print(channel.name + ", " + str(channel.id))
        print("ROLES")
        for role in guild.roles:
            print(role.name + ", " + str(role.id))
        
    @commands.command()
    @has_admin()    
    async def logs(self, ctx):
        """Returns a log from the bot. Initially sends a
        list of all available logs with a selection menu.
        The sender can select a log from the list to have
        the bot attach it to the message.
        """
        page = discord.Embed(title="Questbot Activity Log", description=f"requested by {ctx.message.author.mention}", colour=discord.Colour.dark_red(), type="article")
        page.add_field(name="Available logs", value="`discord`, `database`, `google`, `errors`")
        options = [ # options for the selection menu
            SelectOption(label="bot activity", value="botactions"),
            SelectOption(label="discord", value="discord"),
            SelectOption(label="database", value="database"),
            SelectOption(label="google", value="google"),
            SelectOption(label="errors", value="errors")
            ]
        comp = [[ # selection menu to select which log to attach
                    Select(placeholder="Select an option", options=options)
                ]]
        message = await ctx.send(embed=page, components=comp)
        check = lambda inter: (inter.user.id == ctx.message.author.id
                                and inter.message.id == message.id)
        
        while True:
            try:
                result = await self._bot.wait_for("select_option", check=check, timeout=60.0)
            except asyncio.TimeoutError:
                return
            except Exception as e:
                print(e)
            else:
                fileName = result.values[0]
                with open(f"./logs/{fileName}.log", "rb") as log:
                    attachment = discord.File(log, "logFile.txt")
                    await result.respond(type=4, file=attachment)
                    
    @commands.command(aliases=["accessDB", 'db'])
    @has_admin()
    async def accessDatabase(self, ctx, *, command):
        """Passes a given command into db_interact cog
        to be sent to the database. If the command returns
        values, they are sent to the invoking channel, otherwise
        a simple complete message is sent
        """
        if " -PARAMS " in command:
            items = command.split(" -PARAMS ")
            command = items[0]
            parameters = items[1].split(", ")
        else:
            parameters = ()
            
        result = await self._db._runCommand(command, parameters)
        await ctx.send(result)
                    
    @commands.command()
    @has_admin()
    async def startAnnounceTimer(self, ctx):
        """Starts the announcement cycle timer for the
        announcements cog. Only use this if the timer
        did not start automatically
        """
        self._announcecog.announcementTimer.start()
        
    @commands.command()
    @has_admin()
    async def startUpdateTimer(self, ctx):
        """Starts the update cycle timer for the
        Google_interactions cog. Only use this if the timer
        did not start automatically
        """
        self._updatecog.updateTimer.start()
    
    @commands.command()
    @has_admin()
    async def forceAnnounce(self, ctx):
        """Forces the announcements Cog to make it's announcement cycle"""
        await ctx.send("received")
        await self._announcecog.runAnnouncements()
        await ctx.send("complete")
        
    @commands.command()
    @has_admin()
    async def forceUpdate(self, ctx):
        """Forces the Google_interactions cog to make a full
        update cycle, including the quests, database, and spreadsheet
        """
        await ctx.send("received")
        await self._updatecog.updateQuests()
        await self._updatecog.updateSelf()
        await self._updatecog.updateSpreadsheet()
        await ctx.send("complete")
        
    @commands.command()
    @has_admin()
    async def forceQuests(self, ctx):
        """Forces the Google_interactions cog to update
        the quests, which includes the quest submissions,
        quest list, quest posters, and announcements
        """
        await ctx.send("received")
        await self._updatecog.updateQuests()
        await ctx.send("complete")
        
    @commands.command()
    @has_admin()
    async def forceSelf(self, ctx):
        """Forces the bot to update the database,
        which includes processing all the approved/denied
        quest submissions and any changes made to the member spreadsheet
        """
        await ctx.send("received")
        await self._updatecog.updateSelf()
        await ctx.send("complete")
        
    @commands.command()
    @has_admin()
    async def forceSpreadsheet(self, ctx):
        """Forces the bot to update the members spreadsheet"""
        await ctx.send("received")
        await self._updatecog.updateSpreadsheet()
        await ctx.send("complete")
        
    @commands.command()
    @has_admin()
    async def viewQuestLog(self, ctx, memberId):
        """Sends a request for the bot to upload a member's
        quest log to the master spreadsheet.
        """
        await self._updatecog.uploadSpreadsheet(int(memberId))
        
    @commands.command()
    @has_admin()
    async def adminHelp(self, ctx, command=None):
        """Returns an embed with information on the admin commands.
        If the command parameter is left blank, then the bot returns
        a list of all the commands available. If a command is specified,
        then it returns an article explaining the command and giving an example of it's use
        """
        if command == None:
            page = discord.Embed(title="Admin Commands", description="use |QB adminHelp `command`| for information on a specific command", colour=discord.Colour.dark_red())
            page.add_field(name="Dev tools", value="`sayHi`, `getInfo`, `viewQuestLog`")
            page.add_field(name="Updates", value="`forceAnnounce`, `forceUpdate`, `forceSelf`, `forceQuests`, `forceSpreadsheet`, `accessDatabase`")
            page.add_field(name="Debug", value="`startAnnounceTimer`, `startUpdateTimer`, `logs`")
        else:
            # this dictionary has every admin command, and stores a dictionary with
            # an example and description for the command. Allows the program to easily access
            # the display info for any given command, and easily allows it to check if
            # the given command is legal as well
            commands = {
                "sayHi": {"ex":"QB sayHi", "desc":"Has the bot reply with a generic statement. Used to test if it is currently functioning"},
                "forceAnnounce": {"ex":"QB forceAnnounce", "desc":"Forces the bot to check for and announce any event/weekly quests "
                                  + "which are due to release today. I recommend only using this if the normal announcements do not go off "
                                  + "within ~1 hour of when they are supposed to"},
                "forceUpdate": {"ex":"QB forceUpdate", "desc":"Forces a full update of the system, including updating the quest table, accepting completed quests, "
                                + "changes to the database from the master spreadsheet, and updating the spreadsheets themselves. takes a lot of time and uses a lot of resources. "
                                 +"Only use this when absolutely necessary. See the other force commands for common use"},
                "forceSelf": {"ex":"QB forceSelf", "desc":"Forces an update of the local database for the bot. Includes changes to the database from the master spreadsheet "
                              + "and processing approved/denied quests. I only recommend using this right before doing important work involving someone's info, when you need "
                              + "to make sure everything is up to date"},
                "forceQuests": {"ex":"QB forceQuests", "desc":"Forces an update to the quests. Includes accepting announcements, quest submissions, and updating the quest database"},
                "forceSpreadsheet": {"ex":"QB forceSpreadsheet", "desc":"Forces an update of the master spreadsheet from the database. "
                                     + "Only updates the member spreadsheet with their updated stats, so it is ok to use relatively frequently. "
                                     + "make sure to use this after using the forceSelf command to see the results"},
                "getInfo": {"ex": "QB getInfo", "desc":"Makes the bot print a list containing the name and ID of the server, the channels, and "
                            + "the roles of the server it was called in. The list is printed to standard output, so this method is meant "
                            + "to be used during set up/maintenance"},
                "viewQuestLog": {"ex": "QB viewQuestLog `Member ID`", "desc": "Gathers the quest log of the given member and sends it to "
                                 + "the master spreadsheet"},
                "startAnnounceTimer": {"ex": "QB startAnnounceTimer", "desc": "Forces the announcement system to set a timer "
                                       + "to start it's next update cycle. There is currently no system in place to stop multiple timers "
                                       + "from existing, so only use this method if you are sure the normal update clock did not start on its own"},
                "startUpdateTimer": {"ex": "QB startUpdateTimer", "desc": "Forces the google API system to set a timer "
                                       + "to start it's next update cycle. There is currently no system in place to stop multiple timers "
                                       + "from existing, so only use this method if you are sure the normal update clock did not start on its own"},
                "logs": {"ex": "QB logs", "desc": "Sends a list of available activity logs for the bot with a selection list. "
                         + "Selecting a log from the list will make the bot send an attachment with the log to the list"},
                "accessDatabase": {"ex": "QB accessDatabase `command` -PARAMS `parameters (optional)`",
                                   "desc": "Passes a command into the database. __ONLY USE THIS COMMAND__ IF you know how to use sqlite "
                                   + "and you are a developer for the bot"}
            }
            
            if command in commands:
                page = discord.Embed(title=f"Command info for {command}", description=commands[command]["ex"], colour=discord.Colour.dark_red())
                page.add_field(name="\u200B", value=commands[command]["desc"])
            else:
                page = discord.Embed(title=f"Command info for {command}", description="That command could not be found, try QB help to see a list of all commands", colour=discord.Colour.dark_red())
                
        await ctx.send(embed=page)

class stupidStuff (commands.Cog):
    """This cog just contains stupid stuff I programmed while testing the code
    It doesn't matter, but feel free to add your own stupid stuff while updating/testing
    It helps stop the mental breakdowns
    """
    def __init__(self, bot):
        self._bot = bot
        
    @commands.command()
    async def order (self, ctx, *, meal):
        meal = meal.lower()
        if meal == "bts meal" or meal == "mcdonalds bts meal" or meal == "bts":
            with open("stupidShit\\btsmeal.jpg", "rb") as image:
                attachment = discord.File(image)
        
        await ctx.send("Here's you're food, enjoy!", file=attachment)
        
    @commands.command()
    async def killMe (self, ctx):
        await ctx.send("OK!")
        with open("stupidShit\\gun.png", "rb") as image:
            attachment = discord.File(image)
            
        await ctx.send(file=attachment)
        try:
            await ctx.message.author.kick(reason="You are dead; Not big surprise")
        except Exception as e:
            print(e)
            await ctx.send("*click*\nOh no, no bullets! Oh well, I guess you just have to suffer")
        else:
            await ctx.send("*bang*")

# the token for the discord user the bot runs on.
Token = open("./references/discord_token.txt","r").readline()

intentions = discord.Intents.default()
intentions.members = True

# Create the bot, load all the cogs into it, then run it with the token loaded before
quest_bot = ComponentsBot(command_prefix="QB ", intents=intentions, help_command=None)

#quest_bot.add_cog(stupidStuff(quest_bot)) # dont add this in for any official release
quest_bot.add_cog(google_interact(quest_bot))
quest_bot.add_cog(db_interact(quest_bot, "QuestDB.db"))
quest_bot.add_cog(memb_interact(quest_bot))
quest_bot.add_cog(announceSystem(quest_bot, "QuestDB.db"))
quest_bot.add_cog(admin(quest_bot))

quest_bot.run(Token)
