import discord
import os
from dotenv import load_dotenv
import numpy as np
import asyncio
import json
import pexpect

# requires a local version of the executable logic.exe

exe_file = './logic'
prompt = '>>> '

colors = {'p1': ['b', 'r', 'r', 'b', 'r', 'r'], 'p2': ['r', 'b', 'r', 'b', 'r', 'r'], 'p3': ['r', 'r', 'b', 'b', 'r', 'b'], 'p4': ['b', 'b', 'b', 'b', 'b', 'r']}
your_vals = [2, 2, 6, 8, 9, 10]
turn = 3

logic_prog = None


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

client = discord.Client()
GUILD = os.getenv('DISCORD_GUILD')

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))
    for guild in client.guilds:
        if guild.name == GUILD:
            break

    print(
        f'{client.user} is connected to the following guild:\n'
        f'{guild.name}(id: {guild.id})\n'
    )

    members = '\n - '.join([member.name for member in guild.members])
    print(f'Guild Members:\n - {members}')

async def verify_config():
    global colors
    global your_vals
    global turn

    for color_list in colors.values():
        if len(color_list) != 6:
            return False, 'Color list invalid length (required length of 6)'
        for color in color_list:
            if color not in ['r', 'b']:
                return False, 'Invalid color (r, b)'
    for val in your_vals:
        if val < 1 or val > 12:
            return False, 'Invalid card value (1-12)'
    
    # ensure your values are sorted
    if not all(your_vals[idx] <= your_vals[idx + 1] for idx in range(len(your_vals) - 1)):
        return False, 'Not sorted'

    if turn < 1 or turn > 4:
        return False, 'Invalid turn number'

    return True, 'verified'

# *********************************** WORDHUNT CODE ***********************************************
# generate necessary data for wordhunt

english_words = set()
with open('words.txt', 'r') as f:
    for line in f:
        english_words.add(line.rstrip().lower())

def good_english_word(word):
    # assumes lowercase word
    if len(word) < 3:
        return False
    for char in ['a', 'e', 'i', 'o', 'u', 'y']:
        if char in word:
            return True
    return False

preferred_english_words = set()

for word in english_words:
    if good_english_word(word):
        preferred_english_words.add(word)
    
# possible movements from current character to next character 
possible_deltas = [[0, 1],
                   [1, 1],
                   [1, 0],
                   [1,-1],
                   [0,-1],
                   [-1,-1],
                   [-1,0],
                   [-1,1]]

possible_deltas = [np.array(delta) for delta in possible_deltas]

# Inefficient and bad, but good enough to make the code run fast enough.
# Cannot check for exact matches of a string, but could modify the class to do that by adding a key of 'end' to designate the presence of a word
class LimitedTrie:
    def __init__(self, words) -> None:
        self.root = {}
        for word in words:
            self.add(word)

    def add(self, word):
        current_pos = self.root
        for char in word:
            if char not in current_pos:
                current_pos[char] = {}
            current_pos = current_pos[char]

    def contains_substr(self, word):
        current_pos = self.root
        for char in word:
            if char not in current_pos:
                return False
            else:
                current_pos = current_pos[char]
        return True
            
english_words_trie = LimitedTrie(preferred_english_words)

def is_valid_pos(pos):
    if pos[0] >= 0 and pos[0] <= 3:
        if pos[1] >= 0 and pos[1] <= 3:
            return True
    return False

def conv_pos_to_word(board, positions):
    word = ''
    for pos in positions:
        row, col = pos
        word = word + board[row, col]
    return word

def solve_wordhunt_helper(board, current_pos, prefix_positions, currently_unused):
    """ Returns list of all possible words starting from current position with given prefix """
    global possible_deltas
    global english_words_trie
    rval = []

    # create local copy
    curr_positions = [np.copy(pos) for pos in prefix_positions]
    curr_positions.append(np.copy(current_pos))

    curr_word = conv_pos_to_word(board, curr_positions)

    if not english_words_trie.contains_substr(curr_word):
        return rval

    if curr_word in preferred_english_words:
        rval.append(curr_positions)
        print(curr_word)
    
    for delta in possible_deltas:
        next_pos = current_pos + delta
        next_row, next_col = next_pos
        if is_valid_pos(next_pos) and currently_unused[next_row, next_col]:
            currently_unused[next_row, next_col] = False
            rval = rval + solve_wordhunt_helper(board, next_pos, curr_positions, currently_unused)
            currently_unused[next_row, next_col] = True
  
    return rval

# returns set of words for a board given by letters (a string of 16 chars)
def solve_wordhunt(letters):
    letters = letters.lower()
    board = np.array([char for char in letters])
    board = np.reshape(board, (4, 4))
    all_words_found = []

    for row in range(4):
        for col in range(4):
            currently_unused = np.ones((4,4), dtype=bool)
            currently_unused[row, col] = False
            all_words_found = all_words_found + solve_wordhunt_helper(board, np.array([row, col]), [], currently_unused)
    return all_words_found, board

def format_board(board, bold_positions = None):
    replace_non_bold_with_space = True
    if bold_positions is None:
        replace_non_bold_with_space = False
        bold_positions = []
    # convert to tuples
    bold_positions = [(row, col) for row, col in bold_positions]
    rval = ''
    for row in range(4):
        for col in range(4):
            if (row, col) in bold_positions:
                if (row, col) == bold_positions[0]:
                    rval += board[row, col].upper() + ' '
                else:
                    rval += board[row, col] + ' '
            else:
                if replace_non_bold_with_space:
                    rval += '  '
                else:
                    rval += board[row, col] + ' '
        rval += '\n'
    return rval
# *********************************** WORDHUNT CODE END ***********************************************

@client.event
async def on_message(message):

    global colors
    global your_vals
    global turn
    global logic_prog

    if message.author.bot:
        return

    cmd = message.content.lower().split(' ')

    if not cmd:
        return
    
    if len(cmd) == 2 and cmd[0] == 'wordhunt':
        letters = cmd[1]
        if letters == 'help' or letters == 'h':
            # message style taken from parthiv's help menu https://github.com/parthiv-krishna/stonks-bot/blob/main/stonks-bot.py
            help_menu =  "Usage for wordhunt bot, all commands case insensitive:\n```"
            help_menu += "wordhunt help                       : display this message\n"
            help_menu += "\n### Get List of Longest Words ###\n"
            help_menu += "wordhunt abcdefghijklmnop           : get list of words for the board \n"
            help_menu += "\n"
            help_menu += "                                                   a b c d\n"
            help_menu += "                                                   e f g h\n"
            help_menu += "                                                   i j k l\n"
            help_menu += "                                                   m n o p\n"
            help_menu += "```"
            await message.channel.send(help_menu)
            return
        if len(letters) != 16:
            await message.channel.send('Invalid wordhunt configuration, needs exactly 16 letters with no spaces between the letters, ex: wordhunt abcdefghijklmnop')
            return
        print(f'User requested wordhunt search for {letters}')
        list_of_word_positions, board = solve_wordhunt(letters) 
        list_of_word_positions = sorted(list_of_word_positions, key=lambda word: len(word), reverse=True)

        reduced_list_of_word_positions = []
        already_seen_words = set()
        for positions in list_of_word_positions:
            curr_word = conv_pos_to_word(board, positions)
            if curr_word not in already_seen_words:
                already_seen_words.add(curr_word)
                reduced_list_of_word_positions.append(positions)
            if len(reduced_list_of_word_positions) >= 15:
                break

        results = ''
        for positions in reduced_list_of_word_positions:
            curr_word = conv_pos_to_word(board, positions)
            results += '**' + curr_word + '**' + '\n'
            results += "```"
            results += format_board(board, positions) + '\n'
            results += "```"

        await message.channel.send('**Board:**\n' + "```" + format_board(board) + "```" + '\n' + 'Results:\n\n' + results)
        print('Done finding words')
        return



    if len(cmd) > 1 and cmd[0] == 'logic':
        # parse command, I know this is a mess
        if cmd[1] == 'help' or cmd[1] == 'h':
            # message style taken from parthiv's help menu https://github.com/parthiv-krishna/stonks-bot/blob/main/stonks-bot.py
            help_menu =  "Usage for logic-bot, all commands case insensitive:\n```"
            help_menu += "logic help                          : display this message\n"
            help_menu += "\n### Initial Game Setup ###\n"
            help_menu += "logic config                        : get current (possibly incomplete) configuration\n"
            help_menu += "logic config colors Px R B R B B R  : configure colors for player x (color ordering left to right corresponds to low to high card values)\n"
            help_menu += "logic config values x x x x x x     : configure your card values from low to high\n"
            help_menu += "logic config turn                   : configure initial player turn\n"
            help_menu += "\n### Start/stop program ###\n"
            help_menu += "logic start                         : start the program\n"
            help_menu += "logic stop                          : stop the program\n"
            help_menu += "\n### Default I/O to program ###\n"
            help_menu += "logic X                             : sends X (string or number, no spaces) to the input of the program \n"
            help_menu += "```"
            await message.channel.send(help_menu)
            return
        if cmd[1] == 'config':
            # allow user to set up initial state
            if len(cmd) == 2:
                # print current config, then return
                return_msg = '**Current config**\n' + "```" + 'Colors:\n'

                for player, color_list in colors.items():
                    return_msg += f'{player} has colors (low to high): {" ".join(color_list).upper()}\n'
                
                str_your_values = [str(value) for value in your_vals]
                return_msg += f'You (p1) have card values: {" ".join(str_your_values)}\n'

                return_msg += f'Initial turn: {turn}' + "```"

                await message.channel.send(return_msg)
                return

            if cmd[2] == 'colors':
                # expect logic config colors p1 r b r b b r
                if len(cmd) != 10:
                    await message.channel.send('Unknown command, expected command of format: logic config colors p1 r b r b b r')
                    return
                if cmd[3] not in {'p1', 'p2', 'p3', 'p4'}:
                    await message.channel.send('Unknown player')
                    return
                colors[cmd[3]] = list(cmd[4:])
            elif cmd[2] == 'values':
                # expect logic config values 1 4 5 6 9 12
                if len(cmd) != 9:
                    await message.channel.send('Unknown command, expected command of format: logic config values 1 4 5 6 9 12')
                    return
                your_vals = [int(val) for val in cmd[3:]]
            elif cmd[2] == 'turn':
                # expect logic config turn 3
                if len(cmd) != 4:
                    await message.channel.send('Unknown command, expected command of format: logic config turn 3')
                    return
                turn = int(cmd[3])
            else:
                await message.channel.send('Unknown command, expected command of formad: logic config [colors/values/turn]')
            return

        if cmd[1] == 'quit':
            try:
                if logic_prog.isalive():
                    logic_prog.terminate()
                    return
            except AttributeError:
                pass
            
            await message.channel.send('Program has not even started yet.')
            return

        if cmd[1] == 'start':
            try:
                if logic_prog.isalive():
                    await message.channel.send('Program is already running!')
                    return
            except AttributeError:
                pass

            verified, msg = await verify_config()
            if not verified:
                await message.channel.send(f'Invalid config! Error: {msg}')
                return

            # verified, create init.txt file
            with open('init.txt', 'w') as f:
                f.write('#CARDCOLORS#\n')
                for color_list in colors.values():
                    upper_color_list = [color.upper() for color in color_list]
                    f.write(' '.join(upper_color_list) + '\n')
                f.write('#CARDVALUES#\n')
                str_vals = [str(val) for val in your_vals]
                f.write(' '.join(str_vals) + '\n')
                f.write('#PLAYERTURN#\n')
                f.write(str(turn))
            
            await message.channel.send('Starting program. Program output redirected to discord:')

            logic_prog = pexpect.spawn(exe_file)
            try:
                logic_prog.expect(prompt)
                with open('temp.txt', 'w') as f:
                    f.write(logic_prog.before.decode('utf-8', 'ignore'))
                await message.channel.send('', file = discord.File('temp.txt'))
            except Exception:
                await message.channel.send('Program terminated, invalid configuration.')
            return

        # now in default IO for main part of program, i.e. logic X
        try:
            if not logic_prog.isalive():
                await message.channel.send('Program is not yet running. Start execution with logic start')
                return
        except AttributeError:
            await message.channel.send('Program is not yet running. Start execution with logic start')
            return
        
        usr_inp = str(cmd[1])
        logic_prog.sendline(usr_inp)
        try:
            logic_prog.expect(prompt)
            with open('temp.txt', 'w') as f:
                f.write(logic_prog.before.decode('utf-8', 'ignore')[len(usr_inp):].lstrip().rstrip())
            await message.channel.send('', file = discord.File('temp.txt'))
        except Exception:
            await message.channel.send('Program terminated')
        return

    


client.run(TOKEN)
