#!/usr/bin/python3


import sys
import datetime
import math

import os
import time


OLED_WD=128
OLED_HT=64
OLED_SLAVEADDRESS=0x6a
ADDR_OLED=0x3c

OLED_NUMFONTCHAR=256

OLED_BUFFERIZE = ((OLED_WD*OLED_HT)>>3)
oled_imagebuffer = [0] * OLED_BUFFERIZE

#initialisation de l'écran OLED

    
debug = True

print("-- DEBUG OLED --")

def oled_getmaxY():
    return OLED_HT

def oled_getmaxX():
    return OLED_WD

def oled_loadbg(bgname):
    if (debug): print(f"-- oled_loadbg ({bgname})")



def oled_clearbuffer(value = 0):
    if (debug): print(f"-- oled_clearbuffer {value}")
    return


def oled_writebyterow(x,y,bytevalue, mode = 0):
    if (debug): print(f"-- oled_writebyterow {x},{y}, {bytevalue}, {mode}")

    return 


def oled_writebuffer(x,y,value, mode = 0):
    if (debug): print(f"-- oled_writebuffer {x},{y}, {value}, {mode}")
    return 


def oled_fill(value):
    oled_clearbuffer(value)
    oled_flushimage()

def oled_flushimage(hidescreen = True):
    if (debug): print(f"-- oled_flushimage {hidescreen}")

def oled_flushblock(xoffset, yoffset):
    if (debug): print(f"-- oled_flushblock {xoffset},{yoffset}")
    return


def oled_drawfilledrectangle(x, y, wd, ht, mode = 0):
    if (debug): print(f"-- oled_drawfilledrectangle ({x},{y}) - ({wd},{ht}) # {mode}")
    return
    
def oled_drawline(x, y, wd, ht, mode = 0):
    if (debug): print(f"-- oled_drawline ({x},{y}) - ({wd},{ht}) # {mode}")
    return



def oled_writetextaligned(textdata, x, y, boxwidth, alignmode, charwd = 6, mode = 0):
    leftoffset = 0
    if alignmode == 1:
        # Centered
        leftoffset = (boxwidth-len(textdata)*charwd)>>1
    elif alignmode == 2:
        # Right aligned
        leftoffset = (boxwidth-len(textdata)*charwd)

    oled_writetext(textdata, x+leftoffset, y, charwd, mode)
    

def oled_writetext(textdata, x, y, charwd = 6, mode = 0):
    if (debug): print(f"-- oled_writetext ({x},{y}) \"{textdata}\", size={charwd}")
    return
    

def oled_fastwritetext(textdata, x, y, charht, charwd, fontbytes, mode = 0):
    if (debug): print("-- oled_fastwritetext")
    return


def oled_power(turnon = True):
    if (debug): print(f"-- oled_power {turnon}")
    return



def oled_inverse(enable = True):
    if (debug): print("- oled_inverse")
    return


def oled_fullwhite(enable = True):
    if (debug): print("-- oled_fullwhite")
    return 



def oled_reset():
    if (debug): print("-- oled_reset")

    return

    


