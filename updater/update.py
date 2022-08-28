import sys
import os
import requests

UPDATE_FILE = "updatefile.txt"

def main():
    file_type = ''
    if len(sys.argv) > 1 and sys.argv[1] == 'rerun':
        print('Running pro update')
        with open(UPDATE_FILE) as file:
            for line in file.readlines():
                if line.rstrip() == '':
                    continue
                if file_type == 'POST:':
                    update_file(line)
                if 'POST:' in line:
                    file_type = 'POST:'
    else:
        print('Running pre update')
        with open(UPDATE_FILE, 'r') as file:
            for line in file.readlines():
                if 'POST:' in line:
                    break
                if file_type == 'PRE:':
                    update_file(line)
                if 'PRE:' in line:
                    file_type = 'PRE:'
            

def update_file(URL):
    file_name = get_same_file_dir(URL)
    x = requests.get(URL.rstrip())
    print('\nUpdating: ' + file_name)
    print('from: '+URL.rstrip())
    with open(file_name, 'w', encoding = 'utf-8') as text_file:
        s = x.text
        text_file.write(s.rstrip())

def get_same_file_dir(URL):
    path = os.getcwd()
    parent_path = os.path.abspath(os.path.join(path, os.pardir))
    URL = URL.replace('%20', ' ')
    index = URL.find('FITSSFF Quest System bot/') + 22
    new_path = parent_path + URL[index:]
    new_path = new_path.replace('\n','')
    if '/' in parent_path:
        return new_path.replace('\\','/')
    if '\\' in parent_path:
        return new_path.replace('/','\\')
    return new_path.replace('\\','/')


def test():
    txt = 'https://raw.githubusercontent.com/skyfall1818/MC-Discord-Bot/main/FITSSFF MC discord bot/MC discord bot.py'
    print(len('FITSSFF MC discord bot/'))
    index = txt.find('FITSSFF MC discord bot/') + 23
    
    
if __name__ == "__main__":
    main()
