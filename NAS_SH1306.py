#!/usr/bin/python3


import sys
import datetime
import math

import os

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106

from PIL import Image
from PIL import ImageFont

#import smbus
#import RPi.GPIO as GPIO

#rev = GPIO.RPI_REVISION
#if rev == 2 or rev == 3:
#    bus=smbus.SMBus(1)
#else:
#    bus=smbus.SMBus(0)


OLED_WD=128
OLED_HT=64
OLED_SLAVEADDRESS=0x6a
ADDR_OLED=0x3c

OLED_NUMFONTCHAR=256

OLED_BUFFERIZE = ((OLED_WD*OLED_HT)>>3)
oled_imagebuffer = [0] * OLED_BUFFERIZE

#initialisation de l'écran OLED

serial = i2c(port=7, address=0x3C)
device = sh1106(serial)

mgr = canvas(device)
    
exit = type(mgr).__exit__
draw = type(mgr).__enter__(mgr)

fontSmall  = ImageFont.truetype("fonts/ProggyTiny.ttf", 16)
fontMedium = ImageFont.truetype("fonts/FreePixel.ttf", 16)
fontLarge = ImageFont.truetype("fonts/ProggyTiny.ttf", 22)
debug = False


def oled_getmaxY():
    return OLED_HT

def oled_getmaxX():
    return OLED_WD

def oled_loadbg(bgname):
    if (debug): print(f"-- oled_loadbg ({bgname})")
    if bgname == "bgblack":
        oled_clearbuffer()
        return
    elif bgname == "bgwhite":
        oled_clearbuffer(1)
        return
    try:
        logo = Image.open("oled/"+bgname+".png")
        draw.bitmap((0, 0), logo, fill="white")

    except FileNotFoundError:
        oled_clearbuffer()


def oled_clearbuffer(value = 0):
    if (debug): print(f"-- oled_clearbuffer {value}")
    device.clear()
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

    exit(mgr, None, None, None)


def oled_flushblock(xoffset, yoffset):
    if (debug): print(f"-- oled_flushblock {xoffset},{yoffset}")
    return


def oled_drawfilledrectangle(x, y, wd, ht, mode = 0):
    if (debug): print(f"-- oled_drawfilledrectangle ({x},{y}) - ({wd},{ht}) # {mode}")

    draw.rectangle(xy=[x,y,x+wd,y+ht],outline=mode)

    return
    
def oled_drawline(x, y, wd, ht, mode = 0):
    if (debug): print(f"-- oled_drawline ({x},{y}) - ({wd},{ht}) # {mode}")

    draw.line(xy=[x,y,x+wd,y+ht],fill = 1)

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
    if (charwd == 6):
        fnt = fontSmall
    elif (charwd == 8):        
        fnt = fontMedium
    else:
        fnt = fontLarge

    draw.text(xy=(x,y), text=textdata, fill="white", font=fnt)

    

def oled_fastwritetext(textdata, x, y, charht, charwd, fontbytes, mode = 0):
    if (debug): print("-- oled_fastwritetext")
    return


def oled_power(turnon = True):
    if (debug): print(f"-- oled_power {turnon}")

    if (turnon):
        device.show()
    else:
        device.hide()

    return



def oled_inverse(enable = True):
    if (debug): print("- oled_inverse")
    return


def oled_fullwhite(enable = True):
    if (debug): print("-- oled_fullwhite")
    return 



def oled_reset():
    if (debug): print("-- oled_reset")

    global mgr, exit, draw

    del mgr

    mgr = canvas(device)
    exit = type(mgr).__exit__
    draw = type(mgr).__enter__(mgr)

    return

    


