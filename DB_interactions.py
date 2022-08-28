#===============================================================================
# This file creates the cog which interacts with the quest system database
#
# The program handles all CRUD operations performed on the database,
# aside from what is required for the announcement system.
# This includes anything related to members and quests
#===============================================================================

import discord
from discord.ext import commands
import sqlite3
import datetime
import dateparser
import logging

# member database contents:
# -- adventurers:
# ---- discord ID, first name, last name, discord display name, rank, experience, gold, quests completed
# -- quests:
# ---- number, name, description + non-rank requirements, rank, exp reward, gold reward, type
# -- quest logs:
# ---- quest number, quest name, rank, exp reward, gold reward, type, times completed, date of last completion

class db_interact(commands.Cog):
    """Handles any bot action which involves
    queries made to the database
    """
    def __init__ (self, bot, db_path):
        """Initializes the cog.
        Stores the parent bot and creates a logger and
        references for all local data that is used
        in methods, such as level requirements, rank requirements,
        and the database path. Also checks to make sure the database
        exists in the path.
        """
        self._bot = bot
        self._logger = logging.getLogger('bot activity')
        self._levelref = {} # level requirements
        with open("./references/levels.txt", "r") as file:
            file.readline()
            levelList = file.read().split("\n")
            for item in levelList:
                item = item.split(" - ")
                self._levelref[int(item[0])] = int(item[2])
        self._rankref = {} # rank requirements
        with open("./references/ranks.txt", "r") as file:
            file.readline()
            rankList = file.read().split("\n")
            for item in rankList:
                item = item.split(" - ")
                self._rankref[item[0]] = item[1].split("/")
            
        self._dbpath = db_path
        try:
            test = sqlite3.connect(db_path)
            test.close()
        except Exception as e:
            self._logger.critical("DB_interactions:init:Connection Error: %s", str(e))
    
    @commands.Cog.listener()
    async def on_connect(self):
        """Creates the database connection and cursor and
        gathers a reference for the Google_interactions and
        Member_interactions cogs for use in methods
        """
        self._connection = sqlite3.connect(self._dbpath)
        self._cursor = self._connection.cursor()
        self._api = self._bot.get_cog("google_interact")
        self._members = self._bot.get_cog("memb_interact")
            
    @commands.Cog.listener()
    async def on_ready(self):
        """Gathers a reference to the server once the bot connects"""
        self._guildRef = self._bot.get_guild(236626664304410634)
    
    async def addMember(self, first, last, member, alignment):
        """Adds a member to the quest system database so that
        they can participate in quest and such. The only info
        that needs to be provided is the user's name, alignment,
        and their discord member object; the program will
        gather the rest it needs automatically
        """
        discordID = member.id
        # check if the member has already registered for the quest system. If so,
        # return an error and message the user
        if await self.fetchMember(discordID) != "none found" :
            return("It looks like you're already registered. If you're trying to change your name or alignment,"
                   + " use the `rename` or `realign` commands")
            
        # Gather data for the tuple
        discordName = member.name + "#" + member.discriminator
        date = datetime.date.today().strftime("%m/%d/%Y")
        # Create the tuple to insert into adventurers, and
        # the command which will create the user's quest log
        memberInfo = (discordID, first, last, discordName, alignment, date)
        dbname = str(discordID) + "questLog" # The name of the new table
        
        addCommand = f"""CREATE TABLE '{dbname}' (
                            number INTEGER,
                            name TEXT,
                            rank INTEGER,
                            expReward INTEGER,
                            goldReward INTEGER,
                            type TEXT,
                            timesCompleted INTEGER,
                            dateCompleted NUMERIC
                            )"""
            
        try: # Try adding the adventurer
            self._cursor.execute('INSERT INTO adventurers VALUES (?, ?, ?, ?,"-", ?, 0, 1, 0, "F", "Adventurer", "N/A", "N/A", 0, ?)',
                        memberInfo)
            self._cursor.execute(addCommand)
            await self._members.updateRole(discordID, None, 'F')
        except Exception as e: # If anything fails, rollback and quit
            self._logger.error("DB_interactions:addMember:Insertion Error: %s", str(e))
            self._connection.rollback()
            return('Something went wrong, try again later')
        else: # If not, return a success to the user and commit
            self._connection.commit()
            self._logger.info("DB_interactions:addMember: added values %s to adventurers",
                              str((memberInfo[0], memberInfo[1], memberInfo[2], memberInfo[3], "-",
                              memberInfo[4], 0, 1, 0, "F", "Adventurer", "N/A", "N/A", 0, memberInfo[5])))
            self._logger.info("DB_interactions:addMember: added table %s to database", dbname)
            return(f"Congratulations, {first}! you've been registered to the quest system! "
                   + "Use this private channel to check your stats or change your profile "
                   + "in the guild's archives")
            
    async def deleteMember(self, memberId):
        """Removes a member from the system. It is impossible to get any
        of their info from the system once it is removed, so use this only
        if you have good reason
        """
        memberInfo = await self.fetchMember(memberId)
        dbname = str(memberId) + "questLog"
        
        try:
            self._cursor.execute("DELETE FROM adventurers WHERE ID=?", (memberId,))
            self._cursor.execute(f"DROP TABLE '{dbname}'")
            await self._members.updateRole(memberId, memberInfo[9], None)
        except Exception as e:
            self._logger.error("DB_interactions:deleteMember:Deletion Error: %s", str(e))
            self._connection.rollback()
        else:
            self._logger.info("DB_interactions:deleteMember: removed tuple with ID %s from adventurers", str(memberId))
            self._logger.info("DB_interactions:deleteMember: removed table %s from database", dbname)
            self._connection.commit()
            
    async def editMemberItems(self, memberId, edits: list):
        """Edits a member's record in the database. This can change any column,
        including their experience, titles, ect.
        
        I do not recommend you use it to edit items
        which are independent from quest system, such as their name, discord name, date added, ect.
        Also, do not use this to edit the ID of a user, as the bot will not be able to find them
        in the database afterwards if you do
        
        The items in the edits list are strings in the following format -
        field:newValue
        the value can be lead by a + or - to add or subtract it from
        the current value respectively
        """
        numericFields = ["gold", "exp", "questsCompleted", "level"] # numeric and string fields are treated differently
        try :
            for item in edits: # for each requested edit
                # Separate the fields and values
                edit = item.split(":", 1)
                field = edit[0].lower()
                if field == "# of completed quests" or field == "quests completed":
                    field = "questsCompleted"
                elif field == "discordname" or field == "discord name":
                    field = "discordName"
                
                value = edit[1]
                if field in numericFields: # If it is a numeric field
                    if value.startswith("+") or value.startswith("-"): # Check if the new value is being added/subtracted
                        # Get old value and add the difference
                        original = self._cursor.execute(f"SELECT {field} FROM adventurers WHERE ID=?", (memberId,)).fetchall()[0][0]
                    
                        value = original + int(value)
                    elif value.startswith("'"): # If it is a literal, just remove the apostrophe
                        value = int(value[1:])
                    else: # otherwise, just convert the item
                        value = int(value)
                else: # If it is a string
                    if value.startswith("+"): # If it's being added to the old value
                        # Append it
                        original = self._cursor.execute(f"SELECT {field} FROM adventurers WHERE ID=?", (memberId,)).fetchall()[0][0]
                    
                        value = original + ", " + value
                    elif value.startswith("'"):
                        value = value[1:]
                
                self._cursor.execute(f"UPDATE adventurers SET {field}=? WHERE ID=?", (value, memberId))
        # If any of the edits fails, the bot aborts all edits which would be done.
        # You can edit it to still change other edits, but I do not recommend it
        except Exception as e:
            self._logger.error("DB_interactions:editMemberItems:Update Error: %s", str(e))
            self._connection.rollback()
            return False
        else:
            self._logger.info("DB_interactions:editMemberItems: edited tuple with ID %s with values %s", str(memberId), str(edits))
            self._connection.commit()
            return True
        
    async def questSubmit(self, memberID, questNumber, date):
        """Adds a quest to a member's quest log and edits
        their tuple in the adventurers table to award the
        exp and gold from the given quest. It also
        runs the checkMemberLevel method to update their
        level and rank automatically
        """
        quest = await self.fetchQuest(questNumber) # The quest details
        # If the quest is not found, log and quit
        if quest == "none found" or quest == "error":
            self._logger.warning("DB_interactions:questSubmit:Quit Warning: Could not find quest number %s in database", str(questNumber))
            return False
        member = await self.fetchMember(memberID) # The member's info
        # If the member is not found, log and quit
        if member == "none found" or member == "error":
            self._logger.warning("DB_interactions:questSubmit:Quit Warning: Could not find member with ID %s in database", str(memberID))
            return False
        
        dbname = str(memberID) + "questLog"
        reward = [f"exp:+{quest[4]}", f"gold:+{quest[5]}", "quests completed:+1"] # Made to be used by the editMemberItems method
        # If the member has the quest registered, automatically remove it
        if member[11] == quest[0]:
            reward.append("currentRankedQuest:'N/A")
        elif member[12] == quest[0]:
            reward.append("currentHeroicQuest:'N/A")
        
        try:
            # Send the edit request and quit if it did not finish
            complete = await self.editMemberItems(memberID, reward)
            if not complete:
                self._logger.warning("DB_interactions:questSubmit:Quit Warning: Could not submit reward edits: %s", str(reward))
                return False
            # See if the user has already completed the quest before
            errorType = "Selection"
            present = self._cursor.execute(f"SELECT * FROM '{dbname}' WHERE number=?", (quest[0],)).fetchall()
            if present != []: # If they have, update the times completed
                present = present[0]
                errorType = "Update"
                self._cursor.execute(f"UPDATE '{dbname}' SET timesCompleted=?, dateCompleted=? WHERE number=?", (present[4] + 1, date, quest[0]))
            else: # If not, insert the quest into the table
                errorType = "Insertion"
                self._cursor.execute(f"INSERT INTO '{dbname}' VALUES (?,?,?,?,?,?, ?, ?)", (quest[0], quest[1], quest[3], quest[4], quest[5], quest[6], 1, date))
                
        except Exception as e: # If an error occurs, rollback and quit
            self._logger.error("DB_interactions:questSubmit:%s Error: %s", errorType, str(e))
            self._connection.rollback()
            return False
        
        else: # If not, commit and check the member's level/rank
            self._logger.info("DB_interactions:questSubmit: Updated table %s with quest number %s", dbname, str(questNumber))
            self._connection.commit()
            await self.checkMemberLevel(memberID)
            return True
        
    async def checkMemberLevel(self, memberID):
        """This method ensures the member's level and rank
        match the member's current experience.
        """
        # Fetch the member's info and ensure they exist
        member = await self.fetchMember(memberID)
        if member == "none found" or member == "error":
            self._logger.warning("DB_interactions:checkMemberLevel:Quit Warning: Could not find member with ID %s in database", str(memberID))
            return
        # Get the important info
        memberExp = member[6]
        memberLevel = member[7]
        memberRank = member[9]
        edits = []
        
        # Level Check
        for level, exp in self._levelref.items():
            # Look for a level which is either 1 over the max level
            # or has an exp requirement above the member's exp
            if memberExp < exp or exp < 0:
                if memberLevel != level - 1: # If the member is not the level
                    edits.append("level:" + str(level - 1))
                    number = ((level - 1) // 10) - (memberLevel // 10) # Figure out how many 10s are between the two
                    if number > 0:
                        await self._members.sendCongratMessage(member, "class", number)
                    memberLevel = int(level - 1)
                    
                break
                
        # Rank Check
        for rank, levels in self._rankref.items():
            # Look for a rank where the member's current level is between the
            # level caps of the rank
            if memberLevel >= int(levels[0]) and memberLevel <= int(levels[1]):
                if memberRank != rank:
                    edits.append("rank:" + rank)
                    await self._members.updateRole(memberID, memberRank, rank) # Update the member's role in the server
                    await self._members.sendCongratMessage(member, "rank", rank)
                    
                break
            
        complete = await self.editMemberItems(memberID, edits)
        if not complete:
            self._logger.warning("DB_interactions:checkMemberLevel:Quit Warning: Could not update member ID %s with new level/rank: %s", edits)
        else:
            self._logger.info("DB_interactions:checkMemberLevel: Updated member ID %s with level %s and rank %s", str(memberID), str(memberLevel), memberRank)
            
    async def fetchMember(self, memberID) :
        """Retrieves a single member from the database based on their ID"""
        try :
            memberInfo = self._cursor.execute("SELECT * FROM adventurers WHERE ID=?", (memberID,)).fetchall()
            if memberInfo == []: # If no member is found, update accordingly
                memberInfo = "none found"
            else: # Else, grab the info from the returned list
                memberInfo = memberInfo[0]
        except Exception as e:
            self._logger.error("DB_interactions:fetchMember:Selection Error: %s", str(e))
            return("error")
        else :
            self._logger.info("DB_interactions:fetchMember: gathered member with ID %s from adventurers: %s", str(memberID), str(memberInfo))
            return(memberInfo)
        
    async def fetchMemberName(self, memberName):
        """Retrieves a single member from the database based on their
        discord username. Since this is inherently a much looser identification method
        than using their ID, there is an extra check than what is present in fetchMember.
        Besides that, this method works the same as the one above
        """
        try:
            memberInfo = self._cursor.execute("SELECT * FROM adventurers WHERE discordName LIKE ?", ("%" + memberName + "%",)).fetchall()
            if memberInfo == [] or len(memberInfo) > 1: # If there is any number of members other than 1 returned
                memberInfo = "none found"
            else:
                memberInfo = memberInfo[0]
        except Exception as e:
            self._logger.error("DB_interactions:fetchMemberName:Selection Error: %s", str(e))
            return("error")
        else:
            self._logger.info("DB_interactions:fetchMemberName: gathered member with name %s from adventurers: %s", str(memberName), str(memberInfo))
            return(memberInfo)
         
    async def loadQuests(self, quests):
        try:
            errorType = "Deletion"
            self._cursor.execute("DELETE FROM quests")
            
            errorType = "Insertion"
            self._cursor.executemany("INSERT INTO quests VALUES (?, ?, ?, ?, ?, ?, ?)", quests)
        except Exception as e:
            self._logger.error("DB_interactions:loadQuests:%s Error: %s", errorType, str(e))
            self._connection.rollback()
            return False
        else:
            self._logger.info("DB_interactions:loadQuests: removed all items from quests")
            self._logger.info("DB_interactionsloadQuests: loaded %s new quest(s) into quests\n%s", str(len(quests)), quests)
            self._connection.commit()
            return True
            
    async def fetchQuest(self, questNum):
        """Retrieves a single quest from the database
        based on their quest number. This method works the same
        as the fetchMember method
        """
        try:
            quest = self._cursor.execute("SELECT * FROM quests WHERE number=?", (questNum,)).fetchall()
            if quest == []:
                quest = "none found"
            else:
                quest = quest[0]
        except Exception as e:
            self._logger.error("DB_interactions:fetchQuest:Selection Error: %s", str(e))
            return("error")
        else:
            self._logger.info("DB_interactions:fetchQuest:Selection: selected quest number %s from quests: %s", str(questNum), str(quest))
            return quest
        
    async def getFromTableFilter(self, table: str, args="", fields: tuple=(), fieldTypes: dict={}, shorthands: dict={}, operators: tuple=(), order: str="none"):
        """Retrieves a list of tuples from a given table with a filter
        based on the given arguments. If there are no arguments provided,
        it just retrieves all items with the given order. If you provide arguments,
        you also need to provide fields, fieldTypes, and operators.
        
        fields contains any field you want the args to be able to filter by. This can include any
        column in the table you are searching in.
        
        fieldTypes requires every field in fields to be paired with their type, such as numberic, string, ect.
        
        The shorthands dictionary requires one item, "fields", which contains a dictionary with any fields that have
        a shortened reference. It can also include fields that you want to have shortened values in, like writing "true"
        as "t". To do so, name the item after the field and include a dictionary with any conversions
        
        To see an example of how to format the filtering items, see the questList or questLog methods in
        the Member_interactions cog
        """
        try:
            if args == "": # If no arguments are provided
                if order == "none": # If no order is given, do a basic fetch all
                    command = f"SELECT * FROM '{table}'"
                else: # Else, add the order to the command
                    command = f"SELECT * FROM '{table}' ORDER BY {order}"
                
                items = self._cursor.execute(command).fetchall()
            else: # If there are args
                command = f"SELECT * FROM '{table}' WHERE" # The beginning of the command
                keywords = [] # The search values
                defaultOrder = str(order)
                op = "" # The operator of a given filter
                error = True # If an issue occurs with a keyword, this is used to keep track of it
                # Split the arguments by spaces and sort through the words
                searchField = args.split(" ")
                for item in searchField:
                    # Check if any of the operators are in the word
                    for operator in operators:
                        if operator in item:
                            # If it is, split the word by the operator.
                            # The word to the left of the op is the field,
                            # and the right is the value
                            item = item.split(operator)
                            field = item[0].lower()
                            value = item[1]
                            op = operator # Store the operator
                            if op == ":": # colon is treated as an equal sign 
                                op = "="
                            break
                    if type(item) != type([]): # If the item was not caught by the operator check
                        # check if the item falls under another category for keywords
                        
                        # Writing "sort by x" works the same as using "order=x"
                        # The first two checks handle this function
                        if item == "sort" or item == "ordered" or item == "order":
                            order = "ORDER"
                        elif item == "by" and order == "ORDER":
                            order = "ORDER BY"
                        # writing "descending" or a shorthand of it reverses the ordering
                        elif (item == "descending" or item == "desc" or item == "d") and order != "none":
                            order = order.replace(" ASC", " DESC", 1)
                        # If the first two ordering items were matched, the next non-operator
                        # item is assumed to be the new order
                        elif order == "ORDER BY":
                            order = item + " ASC"
                        # Otherwise, the item is assumed to be a part of the last item added
                        # to the values. Therefore, it is added to the keywords list unless
                        # an error was caught in a previous keyword that hasn't resolved
                        elif not error:
                            keywords[-1] = keywords[-1][:len(keywords[-1]) - 1] + " " + item + "%"
                        continue
                    # If the field is order, set the order
                    if field == "order" or field == "o":
                        order = item[1] + " ASC"
                    else: # The word is a filter
                        # If the field is in shorthands list, apply shorthand conversion
                        if field in shorthands["fields"]:
                            field = shorthands["fields"][field]
                        # check if the field is a valid search field
                        if field not in fields:
                            # If it isn't, log an error and ignore the current word
                            error = True
                            continue
                        
                        #values with special shorthand
                        if field in shorthands:
                            if value in shorthands[field]:
                                value = shorthands[field][value]
                        
                        # numeric values
                        if fieldTypes[field] == "numeric":
                            value = int(value)
                            command = command + f" AND {field}{op}?"
                        # boolean values
                        elif fieldTypes[field] == "bool":
                            if value.lower() == "true" or value.lower() == "yes":
                                value = True
                            elif value.lower() == "false" or value.lower() == "no":
                                value = False
                            command = command + f" AND {field}{op}?"
                        # date values
                        elif fieldTypes[field] == "date":
                            value = dateparser.parse(value).date()
                            command = command + f" AND {field}{op}?"
                        # string and other catchall values
                        else:
                            if op == "=":
                                command = command + f" AND {field} LIKE ?"
                                value = "%" + value + "%"
                            elif op == "!=":
                                command = command + f" AND {field} NOT LIKE ?"
                                value = "%" + value + "%"
                            else:
                                command = command + f" AND {field}{op}?"
                        keywords.append(value)
                        error = False # reset the error from previous words
                        
                # if there are no keywords arguments, meaning the only
                # argument is an order by, I remove the WHERE clause
                if len(keywords) == 0:
                    command = command.replace(" WHERE", "", 1)
                # if at least one keyword argument, cut out the extra AND statement in the command
                else:
                    command = command.replace(" AND", "", 1)
                if order != "none": # if an order was provided
                    if order[:order.index(" ")] in shorthands['fields']: # check for conversion
                        order = shorthands['fields'][order[:order.index(" ")]] + order[order.index(" "):] # replace everything before the ASC/DESC
                    if order[:order.index(" ")] in fields: # if the given order is a valid field
                        command = command + f" ORDER BY {order}"
                    elif defaultOrder != "none":
                        command = command + f" ORDER BY {defaultOrder}"
                
                items = self._cursor.execute(command, keywords).fetchall()
        except Exception as e:
            self._logger.error("DB_interactions:getFromTableFilter:Selection Error: %s", str(e))
            return "error"
        else:
            self._logger.info("DB_interactions:getFromTableFilter: selected items from %s using command %s:\n%s", table, command, str(items))
            return items
    
    async def _runCommand(self, command: str, parameters: ()):
        """Runs a given command from the cursor.
        Designed to be used with the "accessDatabase" command in admin cog
        """
        try:
            self._cursor.execute(command, parameters)
            result = self._cursor.fetchall()
        except Exception as e:
            self._logger.error("DB_interactions:runCommand: %s from %s", str(e), command)
            self._connection.rollback()
            return ("Error: " + str(e))
        else:
            self._logger.info("DB_interactions:runCommand: ran command %s with params %s", command, parameters)
            if result == []:
                self._connection.commit()
                return ("complete")
            else:
                self._connection.commit()
                return ("complete: " + str(result))
