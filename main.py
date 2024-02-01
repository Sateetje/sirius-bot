#!/usr/bin/python

import asyncio
import sys
import validators

def main():

    limit = 100

    start = 1
    stop = 0
    last = 0
    short = False

    state = 0

    for arg in sys.argv[1:]:
        if (state == 0):
            if (arg == '--start'):
                state = 1
            elif (arg == '--stop'):
                state = 2
            elif (arg == '--last'):
                state = 3
            elif (arg == '--short'):
                short = True
        elif (state == 1):
            start = int(arg)
            state = 0
        elif (state == 2):
            stop = int(arg)
            state = 0
        elif (state == 3):
            last = int(arg)
            state = 0

    asyncio.run(validators.report(start, stop, last, short, limit))


if (__name__ == '__main__'):
   main()

