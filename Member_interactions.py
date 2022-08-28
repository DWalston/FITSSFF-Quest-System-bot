#===============================================================================
# This file creates the cog which handles all interactions with members
# in the server
#
# This program handles commands, sending messages to members / the quest system
# channel, and updating member's profiles in the server.
#===============================================================================

# Basic discord imports + discord_components
import discord
from discord.ext import commands
from discord_components import Button, ButtonStyle
# used for interactable elements
import asyncio
# used for image handling
import os.path
import logging

class memb_interact (commands.Cog) :
    """handles any bot action which involves members,
    including messaging, roles, interactive lists, ect.
    """
    
    def __init__ (self, bot) :
        """the initialization method.
        Stores the bot the cog is used in
        """
        self._bot = bot
        self._logger = logging.getLogger('bot activity')
        
    @commands.Cog.listener()
    async def on_connect(self):
        """Used to gather a reference to the DB_interactions
        cog, to use in methods which store / fetch information from
        the database.
        """
        self._db = self._bot.get_cog('db_interact')
        
    @commands.Cog.listener()
    async def on_ready(self) :
        """Prepares all references to the server, including a server ref,
        reference to the bot command channel, and a list of the rank roles.
        It also stores a list of conversions for the ranks when fetching quests
        from the database
        """
        # server reference
        self._guildRef = self._bot.get_guild(236626664304410634)
        # command channel reference
        self._messageChannel = self._guildRef.get_channel(799783089572282378)
        # roles references
        self._rolesref = {}
        with open("./references/roles.txt", "r") as file:
            file.readline()
            roleList = file.read().split("\n")
            for item in roleList:
                item = item.split(" - ")
                if item != ['']:
                    self._rolesref[item[0]] = self._guildRef.get_role(int(item[1]))
        # level exp requirements reference
        self._levelref = {}
        with open("./references/levels.txt", "r") as file:
            file.readline()
            levelList = file.read().split("\n")
            for item in levelList:
                item = item.split(" - ")
                if item != ['']:
                    self._levelref[int(item[0])] = int(item[2])
        # rank translation reference
        self._ranks = {"F":0, "E":1, "D":2, "C":3, "B":4, "A":5, "S":6, "S+":7}
        
    def in_command_channel() :
        """A test predicate to see if a given command was send either
        in the command channel or in a private message. If it was not
        sent from either, the bot will send a message to the channel the command
        was sent from
        """
        async def is_in_channel(ctx):
            member = ctx.message.author
            # if there is no existing message channel between
            # the bot and the user, a channel is created automatically
            if member.dm_channel == None:
                await member.create_dm()

            correctChannel = (ctx.bot.get_guild(236626664304410634).get_channel(799783089572282378).id == ctx.channel.id
                              or ctx.channel.id == member.dm_channel.id)
            if not correctChannel:
                await ctx.bot.get_cog("memb_interact").sendErrorMessage(ctx, "in_command_channel", "wrongChannel")
            return correctChannel
        return commands.check(is_in_channel)
    
    def in_private_channel() :
        """A test predicate which checks if a given command
        was sent from a private channel. If not, a message is sent to the
        channel the command was sent from
        """
        async def is_in_channel(ctx):
            member = ctx.message.author
            # if there is no existing message channel between
            # the bot and the user, a channel is created automatically
            if member.dm_channel == None:
                await member.create_dm()
                
            correctChannel = (ctx.channel.id == member.dm_channel.id)
            if not correctChannel :
                await ctx.bot.get_cog("memb_interact").sendErrorMessage(ctx, "in_private_channel", "publicChannel")
            return correctChannel
        return commands.check(is_in_channel)
    
    @commands.command()
    @in_command_channel()
    async def addMe(self, ctx, first_name, last_name, *, alignment="none specified"):        
        """Registers a user to the quest system database. Takes in the user's preferred
        first and last name and their alignment. The bot will automatically assign the user
        their ID, rank, class, exp/gold, and date joined.
        """
        member = ctx.message.author
        await ctx.send("You want to apply for the guild? Well step into my office, and we can talk")
        
        # Membership check
        if not self._rolesref["Member"] in member.roles or self._rolesref["Eternal Member"] in member.roles:
            await member.send("Sorry, it looks like you're not a member of FITSSFF. In order to sign up "
                              + "for the quest system you need to be a dues paying member. See an officer about "
                              + "paying your dues and officially joining us.")
            return
        
        # sends the member's information to the DB_interactions cog, in order to
        # process their info and add them to the database. A string is returned and
        # sent to the user, which either says they were added successfully, they are
        # already registered, or that an error occured.
        returnstring = await self._db.addMember(first_name, last_name, member, alignment)
        await member.send(returnstring)
        
    @commands.command()
    @in_private_channel()
    async def rename(self, ctx, first_name, last_name) :
        """Changes a user's name in the database.
        Requires the user to provide both a first and last name
        """
        member = ctx.message.author
        # Ensure the member is in the database first
        memberInfo = await self._db.fetchMember(member.id)
        if memberInfo == "none found" or memberInfo == "error":
            await self.sendErrormessage(ctx, "rename", memberInfo)
        
        editField = ["firstname:'" + first_name, "lastname:'" + last_name]
        # send the request to the DB_interactions cog. The cog returns
        # a boolean stating whether the change was successful
        complete = await self._db.editMemberItems(member.id, editField)
        if complete:
            await member.send(f"Your new name has been set successfully, {first_name}!")
        else:
            await self.sendErrorMessage(ctx, "rename")
        
    @commands.command()
    @in_private_channel()
    async def realign(self, ctx, *, alignment):
        """Changes a user's alignment in the database"""
        member = ctx.message.author
        # Ensure the member is in the database first
        memberInfo = await self._db.fetchMember(member.id)
        if memberInfo == "none found" or memberInfo == "error":
            await self.sendErrormessage(ctx, "realign", memberInfo)

        editField = ["alignment:'" + alignment]
        # send the request to the DB_interactions cog. The cog returns
        # a boolean stating whether the change was successful
        complete = await self._db.editMemberItems(member.id, editField)
        if complete:
            await member.send(f"Your alignment has been successfully changed to {alignment}!")
        else:
            await self.sendErrorMessage(ctx, "realign")
        
    @commands.command()
    @in_private_channel()
    #add in exp to next level
    async def getStats(self, ctx) :
        """Returns the user's profile in the database.
        The information returned includes their current title,
        rank, class, experience/gold, and completed quests
        """
        member = ctx.message.author
        
        await ctx.send("I'll grab your file for you")
        # Gethering member's info from the db
        memberInfo = await self._db.fetchMember(member.id)
        # if the member wasn't found or an error occured in the fetch method,
        # the bot sends an error message and quits the command
        if memberInfo == "error" or memberInfo == "none found":
            await self.sendErrorMessage(ctx, "getStats", memberInfo)
        # If not, the bot formats an embed with the member's info and DMs them
        else:
            title = f"{memberInfo[1]} {memberInfo[2]}"
            if memberInfo[4] != '-':
                title = title + f", {memberInfo[4]}"
            nextExp = self._levelref[memberInfo[7] + 1] - memberInfo[6]
            page = discord.Embed(title=title,
                                 description=f"Level {memberInfo[7]} {memberInfo[10]}, Rank {memberInfo[9]}\n{memberInfo[5]}",
                                 colour=discord.Colour.dark_red())
            page.add_field(name=('-' * 50), value=f"Experience: {memberInfo[6]}\nExp to next level: {nextExp}\n"
                                            + f"Gold: {memberInfo[8]}\nQuests completed: {memberInfo[13]}")
            page.set_footer(text=f"joined on {memberInfo[14]}")
            await ctx.send(embed=page)
    
    @commands.command()
    @in_private_channel()
    async def takeQuest(self, ctx, number):
        """Registers a ranked quest for the user.
        The quest is added to the member's tuple in the database
        under the "currentRankedQuest" column.
        """
        # fetch the quest and member
        quest = await self._db.fetchQuest(number)
        member = ctx.message.author
        memberInfo = await self._db.fetchMember(member.id)
        # If the member or quest do not exist, return an error
        if memberInfo == "none found" or memberInfo == "error":
            await ctx.sendErrorMessage(ctx, memberInfo)
        elif quest == "none found" or quest == "error":
            await ctx.send("That quest was not found, sorry")
        # If the quest is not a ranked quest or is a higher rank than the member,
        # reject the request and explain to the member the issue
        elif quest[6] != "ranked":
            await ctx.send("That quest is not a ranked quest, make sure your number is correct")
        elif quest[3] > self._ranks[memberInfo[9]]:
            await ctx.send("You are not a high enough rank to accept this quest")
        else:
            # If the member already has a registered ranked quest, ask them
            # if they want to replace their current quest. If not, quit
            if memberInfo[11] != "N/A":
                comp = [[ # Used for the member to interact with the message
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="✅"), custom_id="yes", disabled=False),
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="❌"), custom_id="no", disabled=False)
                ]]
                message = await ctx.send("You already have an active ranked quest. Accepting this quest will replace it. Do you want to continue?", components=comp)
                check = lambda inter: (inter.user.id == member.id
                                and inter.message.id == message.id) # used to ensure the returned interaction is from the right message + member
                try:
                    # Wait for a response
                    result = await self._bot.wait_for("button_click", check=check, timeout=30.0)
                except Exception as e:
                    print(e)
                except asyncio.TimeoutError: # the request times out
                    return
                else:
                    await result.respond(type=6)
                    if result.custom_id == "no":
                        await message.edit("The quest was not accepted", components=[])
                        return
                    else:
                        await message.edit("Accepting the new quest...", components=[])
            # send the request to the database and return results to user
            complete = await self._db.editMemberItems(member.id, ["currentRankedQuest:" + number])
            if not complete:
                await self.sendErrorMessage(ctx, "takeQuest")
            else:
                await ctx.send(f"You have accepted quest #{number}: {quest[1]}!")
    
    @commands.command()
    @in_private_channel()
    async def takeHeroicQuest(self, ctx, number):
        """Registers a heroic quest for the user.
        The quest is added to the member's tuple in the database
        under the "currentHeroicQuest" column.
        
        This works basically the same as the takeQuest command
        """
        member = ctx.message.author
        memberInfo = await self._db.fetchMember(member.id)
        quest = await self._db.fetchQuest(number)
        if memberInfo == "none found" or memberInfo == "error":
            await ctx.sendErrorMessage(ctx, memberInfo)
        elif quest == "none found" or quest == "error":
            await ctx.send("That quest was not found, sorry")
        elif quest[6] != "heroic":
            await ctx.send("That quest is not a heroic quest, make sure your number is correct")
        elif quest[3] > self._ranks[memberInfo[9]]:
            await ctx.send("You are not a high enough rank to accept this quest")
        else:
            if memberInfo[12] != "N/A":
                comp = [[
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="✅"), custom_id="yes", disabled=False),
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="❌"), custom_id="no", disabled=False)
                ]]
                message = await ctx.send("You already have an active heroic quest. Accepting this quest will replace it. Do you want to continue?", components=comp)
                check = lambda inter: (inter.user.id == member.id
                                and inter.message.id == message.id)
                try:
                    result = await self._bot.wait_for("button_click", check=check, timeout=30.0)
                except Exception as e:
                    print(e)
                except asyncio.TimeoutError:
                    return
                else:
                    await result.respond(type=6)
                    if result.custom_id == "no":
                        await message.edit("The quest was not accepted", components=[])
                        return
                    else:
                        await message.edit("Accepting the new quest...", components=[])
            complete = await self._db.editMemberItems(member.id, ["currentHeroicQuest:" + number])
            if not complete:
                await self.sendErrorMessage(ctx, "takeHeroicQuest")
            else:
                await ctx.send(f"You have accepted heroic quest #{number}: {quest[1]}!")
    
    @commands.command()
    @in_private_channel()
    async def activeQuests(self, ctx):
        """Returns the current registered quests of the user"""
        memberInfo = await self._db.fetchMember(ctx.message.author.id)
        if memberInfo == "error" or memberInfo == "none found":
            await self.sendErrorMessage(ctx, "activeQuests", memberInfo)
        # If the member has no registered quests, send a custom embed
        if memberInfo[11] == "N/A" and memberInfo[12] == "N/A":
            page = discord.Embed(title=f"{memberInfo[1]} {memberInfo[2]}'s active quests",
                             description="It looks like you have no active quests. Try taking one with the `takeQuest` or `takeHeroicQuest` commands",
                             colour=discord.Colour.dark_red())
        else:
            page = discord.Embed(title=f"{memberInfo[1]} {memberInfo[2]}'s active quests",
                             description="\u200B", colour=discord.Colour.dark_red())
            # If the member doesn't have a ranked or heroic quest currently active, specify that
            if memberInfo[11] != "N/A":
                quest = await self._db.fetchQuest(memberInfo[11])
                page.add_field(name="Current Ranked Quest:", value=f"`{quest[0]}` - {quest[1]}\n{quest[2]}")
            # Else, display the quest number, name, and description
            else:
                page.add_field(name="Current Ranked Quest:", value="None\nUse `takeQuest` to take on a ranked quest")
            if memberInfo[12] != "N/A":
                quest = await self._db.fetchQuest(memberInfo[12])
                page.add_field(name="Current Heroic Quest:", value=f"`{quest[0]}` - {quest[1]}\n{quest[2]}")
            else:
                page.add_field(name="Current Heroic Quest:", value="None\nUse `takeHeroicQuest` to take on a Heroic quest")
        
        # Send the embed to the user
        await ctx.send(embed=page)
    
    @commands.command()
    @in_private_channel()
    async def reportQuest(self, ctx) :
        """A simple command used to get the link for the quest submission form"""
        await ctx.send("Ah, a quest to turn in! excellent! Use this form to submit it for review:\nhttps://forms.gle/tyQfWiePudFUSHex7")
        
    @commands.command()
    @in_command_channel()
    async def questList(self, ctx, *, args=""):
        """Used to get a list of quests that are currently in the database
        
        If the args parameter is left blank, then a list of all current quests is returned.
        If not, the returned list is filtered based on what was provided in args
        """
        # Items to be used when searching the database
        fields = ("name", "description", "rank", "expReward", "goldReward", "type")
        fieldTypes = {"name":"string", "description":"string", "rank":"numeric", "expReward":"numeric", "goldReward":"numeric", "type":"string"}
        shorthands = {
                        "fields":{"n":"name", "d":"description", "desc":"description", "r":"rank", "e":"expReward",
                                  "exp":"expReward", "experience":"expReward", "g":"goldReward", "gold":"goldReward", "t":"type"},
                        "type":{"1":"repeatable", "re":"repeatable", "repeat":"repeatable",
                                "2":"ranked", "ra":"ranked",
                                "3":"special", "s":"special", "spec":"special",
                                "4":"heroic", "h":"heroic", "hero":"heroic"},
                        "rank":{"none":-1, "-":-1, "f":0, "e":1, "d":2, "c":3, "b":4, "a":5, "s":6, "s+":7,
                                "F":0, "E":1, "D":2, "C":3, "B":4, "A":5, "S":6, "S+":7}
                      }
        operators = (":", "!=", ">=", "<=", "<", ">", "=")
        order = "number ASC"
        # Send the fetch request to the database
        quests = await self._db.getFromTableFilter("quests", args, fields, fieldTypes, shorthands, operators, order)
        if quests == "error": # If an error occured, resort to an empty list for the quests
            quests = []
        # Create the embed list
        questcount = len(quests)
        ranks = ("F", "E", "D", "C", "B", "A", "S", "S+") # Used to format quests
        page = discord.Embed(title="Quest List", description=f"requested by {ctx.message.author.mention}", colour=discord.Colour.dark_red(), type="article")
        # If there are no quests, create and send a special embed
        if questcount == 0:
            page.add_field(name="\u200B", value="This list is empty")
            page.set_footer(text="0 of 0")
            await ctx.send(embed=page)
        # If there are not enough quests to run an interactive list,
        # simply create and send a single embed with the quests
        elif questcount <= 5:
            for quest in quests:
                firstline = f"*{quest[6]}*"
                if quest[3] >= 0:
                    firstline = firstline + f" - Rank **{ranks[quest[3]]}**"
                page.add_field(name=f"`{quest[0]}` - {quest[1]}",
                           value= firstline + f"""\n`{quest[2]}`
                           awards {quest[4]} exp and {quest[5]} gold""", inline=False)
            page.set_footer(text=f"1 - {questcount} of {questcount}")
            await ctx.send(embed=page)
        else:
            pages = [] # different pages in the list
            pagestart = 0 # used to track where in the list the program is
            while pagestart < (questcount // 5) * 5: # while the bot is under the closest multiple of 5 under the number of quests:
                # take the next 5 quests and add them to the embed
                for i in range(pagestart, pagestart + 5):
                    quest = quests[i]
                    firstline = f"*{quest[6]}*"
                    if quest[3] >= 0:
                        firstline = firstline + f" - Rank **{ranks[quest[3]]}**"
                    page.add_field(name=f"`{quest[0]}` - {quest[1]}",
                                   value=firstline + f"\n`{quest[2]}`\nawards {quest[4]} exp and {quest[5]} gold",
                                   inline=False)
                page.set_footer(text=f"{pagestart + 1} - {pagestart + 5} of {questcount}")
                # add the embed to the page list and create a new embed
                pages.append(page.copy())
                page = discord.Embed(title="Quest List", description=f"requested by {ctx.message.author.mention}", colour=discord.Colour.dark_red(), type="article")
                # Increase the next starting point
                pagestart += 5
                
            for i in range(pagestart, questcount): # add the remaining items in the list to an embed
                quest = quests[i]
                firstline = f"*{quest[6]}*"
                if quest[3] >= 0:
                    firstline = firstline + f" - Rank **{ranks[quest[3]]}**"
                page.add_field(name=f"`{quest[0]}` - {quest[1]}",
                               value=firstline + f"\n`{quest[2]}`\nawards {quest[4]} exp and {quest[5]} gold",
                               inline=False)
            page.set_footer(text=f"{pagestart + 1} - {questcount} of {questcount}")
            pages.append(page.copy())
            
            await self.runList(ctx, pages) # Send the list to be run by the bot
            
    @commands.command()
    @in_command_channel()
    async def questLog(self, ctx, *, args=""):
        """Returns a list with every completed request from a given member
        If a member is not specified, the user that send the command is used
        
        Works fundamentally the same as the questList command, but has different
        fields for the search filters, and a different format for the embed list.
        """
        # Items used to search the database
        fields = ("number", "name", "rank", "expReward", "goldReward", "type", "timesCompleted", "dateCompleted")
        fieldTypes = {"number":"numeric","name":"string", "rank":"numeric", "expReward":"numeric", "goldReward":"numberic",
                      "type":"string", "repeatable":"bool", "timesCompleted":"numeric", "dateCompleted":"date"}
        shorthands = {
                        "fields":{"num":"number", "n":"name", "r":"rank", "e":"expReward", "exp":"expReward", "g":"goldReward", "gold":"goldReward", "t":"type",
                                  "tc":"timesCompleted", "timescompleted":"timesCompleted", "dc":"dateCompleted", "datecompleted":"dateCompleted"},
                        "type":{"1":"repeatable", "re":"repeatable", "repeat":"repeatable",
                                "2":"ranked", "ra":"ranked",
                                "3":"special", "s":"special", "spec":"special",
                                "4":"heroic", "h":"heroic", "hero":"heroic"},
                        "rank":{"none":-1, "-":-1, "f":0, "e":1, "d":2, "c":3, "b":4, "a":5, "a+":6, "s":7,
                                "F":0, "E":1, "D":2, "C":3, "B":4, "A":5, "A+":6, "S":7}
                      }
        operators = (":", "!=", ">=", "<=", "<", ">", "=")
        order = "number ASC"
        # Used to determine if the request is for the user's log
        # or another member's log
        if ctx.message.mentions == []:
            member = ctx.message.author
        else:
            member = ctx.message.mentions[0]
            args = args.replace(member.mention, "").strip()
            
        # The questlog for the requested member
        tableName = str(member.id) + "questLog"
        quests = await self._db.getFromTableFilter(tableName, args, fields, fieldTypes, shorthands, operators, order)
        if quests == "error":
            quests = []
        
        # From this point on, the code works logically the same as questList
        questcount = len(quests)
        page = discord.Embed(title="Quest List", description=f"quests completed by {member.mention}", colour=discord.Colour.dark_red(), type="article")
        if questcount == 0:
            page.add_field(name="\u200B", value="This list is empty")
            page.set_footer(text="0 of 0")
            await ctx.send(embed=page)
        elif questcount <= 5:
            for quest in quests:
                if quest[3] == 1:
                    compRow = f"{quest[6]} times"
                else:
                    compRow = f"on {quest[7]}"
                page.add_field(name=f"`{quest[0]}` - {quest[1]}",
                               value=f"*{quest[5]}* - awarded {quest[3]} exp and {quest[4]} gold\ncompleted {compRow}",
                               inline=False)
            page.set_footer(text=f"1 - {questcount} of {questcount}")
            await ctx.send(embed=page)
        else:
            pages = []
            pagestart = 0
            
            while pagestart < (questcount // 5) * 5:
                for i in range(pagestart, pagestart + 5):
                    quest = quests[i]
                    if quest[3] == 1:
                        compRow = f"{quest[6]} times"
                    else:
                        compRow = f"on {quest[7]}"
                    page.add_field(name=f"`{quest[0]}` - {quest[1]}",
                                   value=f"*{quest[5]}* - awarded {quest[3]} exp and {quest[4]} gold\ncompleted {compRow}",
                                   inline=False)
                page.set_footer(text=f"{pagestart + 1} - {pagestart + 5} of {questcount}")
                pages.append(page.copy())
                page = discord.Embed(title="Quest List", description=f"quests completed by {member.mention}", colour=discord.Colour.dark_red(), type="article")
                pagestart += 5
                
            for i in range(pagestart, questcount):
                quest = quests[i]
                if quest[3] == 1:
                    compRow = f"{quest[6]} times"
                else:
                    compRow = f"on {quest[7]}"
                page.add_field(name=f"`{quest[0]}` - {quest[1]}",
                               value=f"*{quest[5]}* - awarded {quest[3]} exp and {quest[4]} gold\ncompleted {compRow}",
                               inline=False)
                page.set_footer(text=f"{pagestart + 1} - {questcount} of {questcount}")
                pages.append(page.copy())
            
            await self.runList(ctx, pages)
        
    async def runList(self, ctx, pages):
        """Used to run a list which a user can interact with to switch through pages
        
        The method takes in a list of embeds (pages) and displays them for the user with
        buttons attached to allow the user to switch between pages. This method is currently
        only used in conjuction with the questList and questLog commands.
        """
        pagecount = len(pages) # Total number of pages
        pageNum = 0 # current page the user is viewing
        comp = [[ # buttons used for the user to interact with
                    # Since the code starts on the first page, the back and beginning buttons start disabled
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="⏪"), custom_id="start", disabled=True),
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="⬅️"), custom_id="back", disabled=True),
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="➡️"), custom_id="forward", disabled=False),
                    Button(style=ButtonStyle.gray, emoji=discord.PartialEmoji(id=None, name="⏩"), custom_id="end", disabled=False)
                ]]
        # send the first page to the user and wait for a response
        message = await ctx.send(embed=pages[pageNum], components=comp)
        check = lambda inter: (inter.user.id == ctx.message.author.id
                                and inter.message.id == message.id) # Used to ensure the response is from the right message and user
        self._logger.info("Member_interactions:runList: running a list with %s items", len(pages))
        while True: # continuously loop until quit
            try:
                result = await self._bot.wait_for("button_click", check=check, timeout=60.0)
            except asyncio.TimeoutError: # the list times out, quitting the method
                self._logger.info("Member_interactions:runList: list with %s items finished")
                return
            except Exception as e:
                print(e)
            else:
                # Check which button the user pressed and change
                # the current page respectively
                if result.custom_id == "forward":
                    pageNum = min(pageNum + 1, pagecount - 1) # dont allow the user to go above the last page
                elif result.custom_id == "back":
                    pageNum = max(pageNum - 1, 0) # dont allow the user to go below 0
                elif result.custom_id == "start":
                    pageNum = 0
                elif result.custom_id == "end":
                    pageNum = pagecount - 1
            
                # Set the buttons on the message to correspond to
                # what page the user is on
                if pageNum == 0: # first page
                    comp[0][0].disabled=True
                    comp[0][1].disabled=True
                    comp[0][2].disabled=False
                    comp[0][3].disabled=False
                elif pageNum == pagecount - 1: # last page
                    comp[0][0].disabled=False
                    comp[0][1].disabled=False
                    comp[0][2].disabled=True
                    comp[0][3].disabled=True
                else: # in the middle
                    comp[0][0].disabled=False
                    comp[0][1].disabled=False
                    comp[0][2].disabled=False
                    comp[0][3].disabled=False
                    
                # Respond to the interaction and return the new page
                await result.respond(type=6)
                await message.edit(embed=pages[pageNum], components=comp)
    
    @commands.command()
    @in_command_channel()
    async def viewQuest(self, ctx, questNum):
        """Used to view the poster of a given quest"""
        # Gather the quest and check to ensure the quest exists
        quest = await self._db.fetchQuest(questNum)
        if quest == "none found" or quest == "error":
            await ctx.send("Sorry, I can't find any quest with that number. Check your request and try again")
            return
        fileName = f"quest{questNum}.jpg" # the poster's file name
        ranks = ("F", "E", "D", "C", "B", "A", "S", "S+", "Unranked")
        rank = ranks[quest[3]] # The quest's rank
        if os.path.exists(f"./questPics/{rank}/{fileName}"): # Check if the quest's poster is saved to the server
            # Open the image, create an embed to display it, then send it to the user
            self._logger.info("Member_interactions:viewQuest: accessing file quest%s.jpg in read mode", questNum)
            with open(f"./questPics/{rank}/{fileName}", "rb") as image:
                attachment = discord.File(image, filename=fileName)
                page = discord.Embed(title=f"Quest {questNum} - {quest[1]}", description=f"`{quest[6]}`", 
                                     colour=discord.Colour.dark_red(), type="image")
                page.set_image(url=f"attachment://{fileName}")
                await ctx.send(file=attachment, embed=page)
        else: # If the poster is not found, inform the user and (possibly) inform someone in quest system goblins
            await ctx.send("While that quest exists, I can't seem to find the poster for it. I'll let the higher ups know "
                           + "about this, try coming back in a bit")
    
    @commands.command()
    @in_command_channel()
    async def help(self, ctx, command=None):
        """Returns a list of all available commands for users. The user
        can specify a command to see a description and example of the command
        """
        member = ctx.message.author
        if member.dm_channel == None:
                await member.create_dm()
                
        if not ctx.channel.id == member.dm_channel.id:
            await ctx.send("Need help? OK! check your DMs for the guide")
        
        if command == None: # Basic list of commands available to members
            page = discord.Embed(title="Commands", description="use |QB help `command`| for information on a specific command", colour=discord.Colour.dark_red())
            page.add_field(name="Members", value="`addMe`, `getStats`, `realign`, `rename`, `activeQuests`") # commands for member information
            page.add_field(name="Quests", value="`viewQuest`, `questList`, `questLog`") # commands to see quests
            page.add_field(name="Quest reporting", value="`reportQuest`, `takeQuest`, `takeHeroicQuest`") # commands to take and complete quests
        else:
            commands = { # this dictionary has every command paired to an example and description.
                "addMe": {"ex":"QB addMe `first name` `last name` `alignment [optional]`", "desc":"Registers you to the quest system! You'll start out as a level 1 adventurer,"
                          + " but you'll rise in the ranks quickly once you start completing quests"},
                "getStats": {"ex":"QB getStats", "desc":"Retrieves your stats from the quest system's files"},
                "realign": {"ex":"QB realign `alignment`", "desc":"Changes your alignment in the quest system's files. We'd prefer if you stick to the typical alignment chart,"
                            + " but we can't really stop you from not doing that either"},
                "rename": {"ex":"QB rename `first name` `last name`", "desc":"changes your name in the quest system's files. Please don't be immature about this or we will remove you"},
                "activeQuests": {"ex":"QB activeQuests", "desc":"Displays the current ranked and heroic quests you have taken"},
                "viewQuest": {"ex":"QB viewQuest `quest number`", "desc":"Displays the poster for the given quest"},
                "questList": {"ex":"QB questList `filters [optional]`", "desc":"Look up a list of quests."
                            +" If no filter is provided, it will return a list of all quests currently available\n"
                            + "```diff\n-FILTERS\nname {shorthands: n}\ndescription {shorthands: d, desc}\nrank {shorthands: r}\n"
                            + "experience {shorthands: e, exp}\ngold {shorthands: g}\ntype {shorthands: t}\n\n-SORTING\n"
                            + "sort by [field] [descending]\norder=[field] [desc]\no=[field] [d]\n\n-OPERATIONS\n=, !=, >, <, >=, <=```"},
                "questLog": {"ex":"QB questLog `user [optional]` `filters [optional]`", "desc":"Retrieves the list of quests completed by a user. "
                            + "If a user isn't provided, then the quest log of the member who used the command is retrieved.\n"
                            + "```diff\n-FILTERS\nnumber {shorthands: num}\nname {shorthands: n}\nrank {shorthands: r}\nexp {shorthangs: e}\ngold {shorthands: g}\n"
                            + "type {shorthands: t}\ntimescompleted {shorthands: tc}\ndatecompleted {shorthands: dc}\n\n-SORTING\nsort by [field] [descending]"
                            + "order=[field] [desc]\no=[field] [d]\n\n-OPERATIONS'n=, !=, >, <, >=, <=```"},
                "reportQuest": {"ex":"QB reportQuest", "desc":"Gives you the form to report a completed quest to the quest masters"},
                "takeQuest": {"ex":"QB takeQuest `quest number`", "desc":"registers the given quest as your active ranked quest. You need to register "
                              + "a ranked quest before attempting it. If you already have an active quest, you will be asked to confirm if you want to switch to the new quest"},
                "takeHeroicQuest": {"ex":"QB takeHeroicQuest `quest number`", "desc":"registers the given quest as your active heroic quest. You need to register "
                              + "a heroic quest before attempting it. If you already have an active heroic quest, you will be asked to confirm if you want to switch to the new quest"}
                }
            if command in commands: # If the given command is in the dictionary, return it's info
                page = discord.Embed(title=f"Command info for {command}", description=commands[command]["ex"], colour=discord.Colour.dark_red())
                page.add_field(name="\u200B", value=commands[command]["desc"])
            else: # Else, return an error
                page = discord.Embed(title=f"Command info for {command}", description="That command could not be found, try `QB help` to see a list of all commands", colour=discord.Colour.dark_red())
                
        await member.send(embed=page) # Return the information
        
    async def updateRole(self, memberID, oldrole, newrole):
        """Used to update a member's role when they rank up"""
        member = self._guildRef.get_member(memberID)
        if oldrole != None:
            await member.remove_roles(self._rolesref[oldrole])
        if newrole != None:
            await member.add_roles(self._rolesref[newrole])
        
    async def sendCongratMessage(self, memberInfo, messageType, info):
        """Used to inform a member that they have reached a special milestone
        in their level, which is either a class promotion or a rank up.
        
        The info parameter is used for additional information that's needed for the message.
        What info does for each type of message is explained in the comments
        """
        member = self._guildRef.get_member(memberInfo[0])
        if messageType == "rank": # Info is the member's new rank
            await member.send(f"Congratulations, {memberInfo[1]}! You have earned enough Exp to reach rank {info}! "
                              + f"You can now take any quest that is rank {info} or lower")
        elif messageType == "class": # Info is the number of times the member was promoted since the last message
            for i in range(info):
                await member.send(f"Congratulations, {memberInfo[1]}! You have earned enough Exp to earn a new Class Promotion! "
                                  + "Please see the class tree to see what promotions you can take, then message a member of "
                                  + "the quest committee to confirm your new class")
    
    async def sendErrorMessage(self, ctx, command, errorType="unknown") :
        """Used to send error messages for general problems,
        Such as a command being send to the wrong channel
        """
        if errorType == "publicChannel" :
            self._logger.warning("Member_interactions:%s:Quit Warning: DM command sent into a public channel by %s", command, ctx.message.author.name)
            await ctx.send("I'm sorry, but I can only fulfill private requests like this from my office. Please DM me this command so I can fulfill it for you")
        elif errorType == "wrongChannel" :
            self._logger.warning("Member_interactions:%s:Quit Warning: command sent into non-command channel by %s", command, ctx.message.author.name)
            await ctx.send(f"I only accept commands from the {self._messageChannel.mention} channel! Please give me your requests there")
        elif errorType == "none found" :
            self._logger.warning("Member_interactions:%s:Quit Warning: User %s not part of the quest system", command, ctx.message.author.name)
            await ctx.send(f"It looks like you haven't registered to the quest system yet! Use the `addMe` command in {self._messageChannel.mention} to be added to the guild")
        else :
            self._logger.warning("Member_interactions:%s:Quit Warning: unknown error forced command to quit", command)
            await ctx.send("Sorry, something unknown went wrong. Please give the code monkeys some time to fix it and try again later")
