def confirm(msg):
    res = input(msg + '[Y/n] ').lower()
    return res == 'y'
