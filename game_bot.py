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

def solve_wordhunt_helper(board, current_pos, prefix, currently_unused):
    """ Returns set of all possible words starting from current position with given prefix """
    global possible_deltas
    global english_words_trie
    rval = set()

    curr_row, curr_col = current_pos
    curr_word = prefix + board[curr_row, curr_col]

    if not english_words_trie.contains_substr(curr_word):
        return rval

    if curr_word in preferred_english_words:
        rval.add(curr_word)
        print(curr_word)
    
    for delta in possible_deltas:
        next_pos = current_pos + delta
        next_row, next_col = next_pos
        if is_valid_pos(next_pos) and currently_unused[next_row, next_col]:
            currently_unused[next_row, next_col] = False
            rval = rval.union(solve_wordhunt_helper(board, next_pos, curr_word, currently_unused))
            currently_unused[next_row, next_col] = True
  
    return rval

# returns set of words for a board given by letters (a string of 16 chars)
def solve_wordhunt(letters):
    letters = letters.lower()
    board = np.array([char for char in letters])
    board = np.reshape(board, (4, 4))
    all_words_found = set()

    for row in range(4):
        for col in range(4):
            currently_unused = np.ones((4,4), dtype=bool)
            currently_unused[row, col] = False
            all_words_found = all_words_found.union(solve_wordhunt_helper(board, np.array([row, col]), '', currently_unused))
    return all_words_found, board

def format_board(board):
    rval = ''
    for row in board:
        for char in row:
            rval += char + ' '
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
        if len(letters) != 16:
            await message.channel.send('Invalid wordhunt configuration, needs 16 letters with no spaces between the letters, ex: wordhunt abcdefghijklmnop')
            return
        print(f'User requested wordhunt search for {letters}')
        words, board = solve_wordhunt(letters)
        words = list(words)
        words = sorted(words, key=lambda word: len(word), reverse=True)
        words = words[:min(40, len(words))]
        results = '\n'.join(words)
        await message.channel.send(f'**Board:\n{format_board(board)}**\n' + 'Results:\n\n' + results)
        print('Done finding words')



    if len(cmd) > 1 and cmd[0] == 'logic':
        # parse command, I know this is a mess
        if cmd[1] == 'config':
            # allow user to set up initial state
            if len(cmd) == 2:
                # print current config, then return
                return_msg = '**Current config**\n' + 'Colors:\n'

                for player, color_list in colors.items():
                    return_msg += f'{player} has colors (low to high): {" ".join(color_list)}\n'
                
                str_your_values = [str(value) for value in your_vals]
                return_msg += f'You have card values: {" ".join(str_your_values)}\n'

                return_msg += f'Initial turn: {turn}'

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
            logic_prog.expect(prompt)
            with open('temp.txt', 'w') as f:
                f.write(logic_prog.before.decode('utf-8', 'ignore'))
            await message.channel.send('', file=discord.File('temp.txt'))
            return

        # now in default IO for main part of program
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
            await message.channel.send('', file=discord.File('temp.txt'))
        except Exception:
            await message.channel.send('Program terminated')
        return

    


client.run(TOKEN)
