#!/usr/bin/python3

#
# This script set fan speed and monitor power button events.
#
# Fan Speed is set by sending 0 to 100 to the MCU (Micro Controller Unit)
# The values will be interpreted as the percentage of fan speed, 100% being maximum
#
# Power button events are sent as a pulse signal to BCM Pin 4 (BOARD P7)
# A pulse width of 20-30ms indicates reboot request (double-tap)
# A pulse width of 40-50ms indicates shutdown request (hold and release after 3 secs)
#
# Additional comments are found in each function below
#
# Standard Deployment/Triggers:
#  * Raspbian, OSMC: Runs as service via /lib/systemd/system/argononed.service
#  * lakka, libreelec: Runs as service via /storage/.config/system.d/argononed.service
#  * recalbox: Runs as service via /etc/init.d/
#

# For Libreelec/Lakka, note that we need to add system paths
# import sys
# sys.path.append('/storage/.kodi/addons/virtual.rpi-tools/lib')
# import RPi.GPIO as GPIO


from pathlib import Path
import sys
import os
import time
import re

from threading import Thread
from queue import Queue

#sys.path.append("/etc/argon/")
from sysInfo import *
from NASlog import *
from NASconfig import *
from NASversion import *

isRoot, isArmbian = checkPrivilege()
print(f"\nisRoot {isRoot}  isArmban {isArmbian}\n")
if ((not isRoot) and isArmbian):
    print("NAS must be executed with Root privilege")
    exit(-1)

if isArmbian: 
    import mraa


# rev = GPIO.RPI_REVISION
# if rev == 2 or rev == 3:
#    bus=smbus.SMBus(1)
# else:
#    bus=smbus.SMBus(0)
OLED_ENABLED = False
MAX_WARNING  = 50

OFF   = 0
BLINK = 1
ON    = 2


#
# Enable logging
#

if isArmbian: 
    import datetime
    from NAS_SH1306 import *
    OLED_ENABLED=True
else:
    import datetime
    from NAS_trace import *
    OLED_ENABLED=True


devices, sizes   = getDevices()
names, smartAttrs, sumup = getDevicesSmartsAttr(devices['hd'])
mapping = getDevicesMapping(devices['hd'])

#
# Enable debug logging if requested
#
#enableLogging( loadDebugMode() )

#ADDR_FAN=0x1a
PIN_BUTTON   = 15   

# initialise PWM & period
if isArmbian:
    fanPwm = mraa.Pwm(11)
    fanPwm.period_us(40)
    fanPwm.enable(True)

def ledDriver(q):
   
    led = {'ata1':29, 'ata2':31, 'ata3':33, 'ata5':35, 'ata4':37, 'blue':16, 'red':18}
    
    for i in led:
        if isArmbian:
            led[i] = {'io':mraa.Gpio(led[i]), 'state':0, 'pattern':OFF}
            led[i]['io'].dir(mraa.DIR_OUT)
        else:
            led[i] = {'state':0, 'pattern':OFF}

    print(f"LED driver : started ")
    led['blue']['pattern'] = ON
    
    while True:
        for i in led:
            dev = led[i]

            if dev['pattern'] == ON:     dev['state'] = 0
            if dev['pattern'] == BLINK:  dev['state'] = (dev['state']+1) % 2
            if dev['pattern'] == OFF :   dev['state'] = 1

            if isArmbian:
                dev['io'].write(dev['state'])            

        time.sleep(1)

        if q.empty() == False:
            data = q.get()
            #print(f"LED Driver : new Event {data}")

            if (data[0] == '- OK -'):
                led['blue']['pattern'] = ON
                led['red']['pattern']  = OFF                
                for i in data[1]:
                    led[i]['pattern'] = 0
                        

            if (data[0] == 'ERROR'):
                led['blue']['pattern'] = OFF
                led['red']['pattern']  = ON                 
                for i in data[1]:
                    led[i]['pattern'] = data[1][i]


            if (data[0] == 'WARNING'):
                led['blue']['pattern'] = ON
                led['red']['pattern']  = ON                 
                for i in data[1]:
                    led[i]['pattern'] = data[1][i]

def read_key(pattern, size):
    if isArmbian:
        s = ''
        pin15 = mraa.Gpio(PIN_BUTTON)
        pin15.dir(mraa.DIR_IN)

        while True:
            s = s[-size:] + str(pin15.read())
            #print(s)
            time.sleep(0.1)
            for t, p in pattern.items():
                if p.match(s):
                    return t

def watch_key(q):
    size = 7
    wait = 3
    pattern = {
        'click' : re.compile(r'1+0+1{%d,}' % wait),
        'twice' : re.compile(r'1+0+1+0+1{%d,}'% wait),
        'triple': re.compile(r'1+0+1+0+1+0+1{%d,}' % wait),
        'press' : re.compile(r'0{%d,}' % size),
    }
    while True:
        q.put(read_key(pattern, 10))


# This function is the thread that monitors temperature and sets the fan speed
# The value is fed to get_fanspeed to get the new fan speed
# To prevent unnecessary fluctuations, lowering fan speed is delayed by 30 seconds
#
# Location of config file varies based on OS
#

def setFanOff ():
    setFanSpeed (overrideSpeed = 0)

def setFanFlatOut ():
    setFanSpeed (overrideSpeed = 100)

def setFanSpeed (overrideSpeed : int = None, instantaneous : bool = True):
    """
    Set the fanspeed.  Support override (overrideSpeed) with a specific value, and 
    an instantaneous change.  Some hardware does not like the sudden change, it wants the
    speed set to 100% THEN changed to the new value.  Not really sure why this is.
    """

    def getFanSpeed(tempval, configlist):
        """
        This function converts the corresponding fanspeed for the given temperature the
        configutation data is a list of strings in the form "<temperature>:<speed>"
        """
        retval = 0
        if len(configlist) > 0:
            for k in configlist.keys():
                if tempval >= float(k):
                    retval=int(configlist[k])
                    logDebug( "Temperature (" + str(tempval) + ") >= " + str(k) + " suggesting fanspeed of " + str(retval) )
        logDebug( "Returning fanspeed of " + str(retval))
        return retval


    if overrideSpeed is not None:
        newSpeed = overrideSpeed
    else:
        newSpeed = max([getFanSpeed(getCPUusage()['temp'], loadCPUFanConfig())
                       ,getFanSpeed(sumup['maxTemp'], loadHDDFanConfig())
                       ]
                      )
        if newSpeed < setFanSpeed.prevSpeed and not instantaneous:
            # Pause 30s before speed reduction to prevent fluctuations
            time.sleep(30)

    # Make sure the value is in 0-100 range
    newSpeed = max([min([100,newSpeed]),0])
    if overrideSpeed is not None or (setFanSpeed.prevSpeed != newSpeed):
        try:
            if setFanSpeed.prevSpeed == 0:
                # Spin up to prevent issues on older units                
                print(f"FAN starts")
                if isArmbian: 
                    fanPwm.write(0.5)
                time.sleep(2)
                

            print(f"FAN speed {newSpeed} -  {1-newSpeed/100.0}))")

            if isArmbian:
                fanPwm.write(1-newSpeed/100.0)

            logging.debug( "writing to fan port, speed " + str(newSpeed))
            setFanSpeed.prevSpeed = newSpeed

        except IOError:
            logError( "Error trying o update fan speed.")
            return setFanSpeed.prevspeed
    return newSpeed
setFanSpeed.prevSpeed = 0

def temp_check():
    """
    Main thread for processing the temperature check functonality.  We just try and set the fan speed once
    a minute.  However we do want to start with the fan *OFF*.
    """
    setFanOff()
    while True:
        setFanSpeed (instantaneous = False)
        time.sleep(5)
#
# This function is the thread that updates OLED
#
def display_loop(readq, writeq):
    weekdaynamelist = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    monthlist = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    oledscreenwidth = oled_getmaxX()


    global devices, sizes
    global names, smartAttrs, sumup
    global mapping

    fontwdSml = 6    # Maps to 6x8
    fontwdReg = 8    # Maps to 8x16
    fontwdLrg = 10    # Maps to 8x16
    stdleftoffset = 54

    temperature="C"
    temperature = loadTempConfig()

    print( "Temperature config is " + temperature )
    screensavermode = False
    screensaversec = 120
    screensaverctr = 0

    screenenabled = ["clock", "ip"]
    prevscreen = ""
    curscreen = ""
    screenid = 0
    screenjogtime = 0
    screenjogflag = 0  # start with screenid 0
    cpuusagelist = []
    curlist = []
    cpuGraph = []

    for i in range (30):
        cpuGraph.append(0)

    tmpconfig=loadOLEDConfig()  

    if "screensaver" in tmpconfig:
        screensaversec = int(tmpconfig["screensaver"])
    if "screenduration" in tmpconfig:
        screenjogtime = int(tmpconfig["screenduration"])
    if "screenlist" in tmpconfig:
        screenenabled = tmpconfig["screenlist"].replace("\"","").split(" ")
        print (f"Screen : {screenenabled}")
    if "enabled" in tmpconfig:
        if tmpconfig["enabled"] == "N":
            screenenabled = []

    #
    # Setup some variables to help calculate bandwidth
    #
    timespan = 1
    deviceActivityPrev = getDeviceActivty(devices['mnt'])
    deviceUsage        = getDeviceUsage(devices['mnt'])
    prevTime = time.clock_gettime_ns(time.CLOCK_MONOTONIC)

    while len(screenenabled) > 0:
        if len(curlist) == 0 and screenjogflag == 1:
            # Reset Screen Saver
            # screensavermode = False
            # print("reset screensaverctr")
            # screensaverctr = 0

            # Update screen info
            screenid = screenid + screenjogflag
            if screenid >= len(screenenabled): screenid = 0

        prevscreen = curscreen
        if (curscreen != 'reboot'): curscreen = screenenabled[screenid]

        #print( curscreen )
        if screenjogtime == 0:
            # Resets jogflag (if switched manually)
            screenjogflag = 0
        else:
            screenjogflag = 1

        if (int(time.strftime("%M")) == 0):
            devices, sizes   = getDevices()
            names, smartAttrs, sumup = getDevicesSmartsAttr(devices['hd'])
            mapping = getDevicesMapping(devices['hd'])            

        needsUpdate = False
        if   curscreen == "cpu": 
            # CPU Usage
            
            try:                
                cpuusagelist = getCPUusage()                    
            except:
                logError( "Error processing information for CPU display")

            
            oled_loadbg("bgcpu")    
            avg = cpuusagelist['load']

            oled_writetextaligned(f"{avg:02}%", stdleftoffset, 4, oledscreenwidth-stdleftoffset, 1, fontwdReg)

            if (len(cpuGraph) > 30): cpuGraph = cpuGraph[1:]
            cpuGraph.append(avg)

            for i in range(len(cpuGraph)):
                oled_drawfilledrectangle(stdleftoffset+4+i*2, 55, 1, -1*int((cpuGraph[i]/4)),2)

            oled_drawline(stdleftoffset+4, 58, 61, 0,1)
            oled_drawline(stdleftoffset+4, 23, 61, 0,1)
            
            needsUpdate = True
            curlist = []           
        elif curscreen == "storage": 
            # Storage Info           
            deviceUsage = getDeviceUsage(devices['mnt'])
            
            oled_loadbg("bgstorage")

            yoffset = 16
            for curDev in deviceUsage:
                # Right column first, safer to overwrite white space
                oled_writetextaligned(deviceUsage[curDev]['total'], 85, yoffset, oledscreenwidth-85, 2, fontwdSml)
                oled_writetextaligned(str(deviceUsage[curDev]['percent'])+"%", 60, yoffset, 90-60, 2, fontwdSml)
                tmpname = curDev
                if len(tmpname) > 8:
                    tmpname = tmpname[0:8]
                oled_writetext(tmpname, 0, yoffset, fontwdSml)

                yoffset = yoffset + 16
        
            needsUpdate = True
            curlist = []          
        elif curscreen == "bandwidth": 
            # Bandwidth info            
            deviceActivity = getDeviceActivty(devices['mnt'])
            stoptime  = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
            timespan = (stoptime - prevTime)/1000000000
            prevTime  = stoptime    

            oled_clearbuffer()
            oled_writetextaligned( "BANDWIDTH", 0, 0, oledscreenwidth, 1, fontwdSml)
            oled_writetextaligned( "Write", 90, 16, oledscreenwidth-90, 2, fontwdSml)
            oled_writetextaligned( "Read",  60, 16, 90-60,              2, fontwdSml)
            oled_writetext( "Device", 0, 16, fontwdSml )

            itemcount = 2
            yoffset   = 32
         
            for device in deviceActivity:
                curr = deviceActivity[device]
                prev = deviceActivityPrev[device]
                '''
                if device == 'md0':
                    print(f" WRiTE {device}  curr:{curr['write']}  prev:{prev['write']} speed {(curr['write']-prev['write'])/timespan} Time:{timespan}")
                    print(f" READ  {device}  curr:{curr['read']}   prev:{prev['read']}  speed {(curr['read']-prev['read'])/timespan} Time:{timespan}")
                '''

                bandwidth = int(((curr['write']-prev['write']))/(timespan*2))
                oled_writetextaligned( kbstr(bandwidth,False), 90, yoffset, oledscreenwidth-90, 2, fontwdSml )

                bandwidth = int(((curr['read']-prev['read']))/(timespan*2))
                oled_writetextaligned( kbstr(bandwidth,False), 60, yoffset, 90-60, 2, fontwdSml )

                oled_writetext( device, 0, yoffset, fontwdSml )
                itemcount = itemcount - 1
                yoffset   = yoffset + 16            
            
            deviceActivityPrev  = deviceActivity         
            needsUpdate = True
            curlist = []
        elif curscreen == "raid":  
            # Raid Info
            
            raid = getRAID()
            raidName = list(raid.keys())[0]
            raid = raid[raidName]
            
            oled_loadbg("bgraid")
            oled_writetextaligned(raidName, 0, 0, stdleftoffset, 1, fontwdSml)
            oled_writetextaligned(raid["type"], 0, 8, stdleftoffset, 1, fontwdSml)
            if raidName in sizes:
                oled_writetextaligned(sizes[raidName], 0, 56, stdleftoffset, 1, fontwdSml)
            else:
                oled_writetextaligned("----", 0, 56, stdleftoffset, 1, fontwdSml)
            oled_writetext( raid['status'], stdleftoffset, 4, fontwdReg )
            if raid['recovery'] != None:
                oled_writetext(f"{raid['recovery']['percentage']}% at {raid['recovery']['speed']}", stdleftoffset, 16, fontwdSml)
            oled_writetext(f"Active  : {raid['disc'][0]}", stdleftoffset, 28, fontwdSml)
            oled_writetext(f"Working : {raid['disc'][1]}", stdleftoffset, 38, fontwdSml)
            oled_writetext(f"Failed  : {raid['disc'][0]-raid['disc'][1]}", stdleftoffset, 48, fontwdSml)
            # oled_writetext("Failed  : "+str(int(tmpitem["info"]["failed"]))+"/"+str(int(tmpitem["info"]["devices"])), stdleftoffset, 48, fontwdSml)
            needsUpdate = True            
        elif curscreen == "smart": 
            # Raid Info         
            oled_loadbg("bgdisc")
            led = {}
               
            if    sumup['error']   >  0: 
                msg = "ERROR"
            elif  sumup['warning'] >  MAX_WARNING: 
                msg = "WARNING"
            else: 
                msg = "- OK -"  
        

            yoffset = 0
            for dev in smartAttrs:
                oled_writetext(dev, 56, yoffset, fontwdSml)
                oled_writetextaligned(f"{smartAttrs[dev]['warning']}",75,yoffset,20, 2, fontwdSml)    
                oled_writetextaligned(f"{smartAttrs[dev]['error']}",90,yoffset,30, 2, fontwdSml)    
                yoffset += 12

            '''
            oled_writetextaligned(msg, stdleftoffset, 8, oledscreenwidth-stdleftoffset, 1, fontwdReg)

                
            
            if msg == "- OK -":
               
                
                devStb = getDevicesStandby(devices['hd'])
                idle = 0
                for stb in devStb:
                    if devStb[stb]: idle += 1

                oled_writetextaligned(f"Idle   {idle}", stdleftoffset, 36, oledscreenwidth-stdleftoffset, 1, fontwdSml)
                oled_writetextaligned(f"Active {len(devStb)-idle}", stdleftoffset, 48, oledscreenwidth-stdleftoffset, 1, fontwdSml)
                

            if msg == "WARNING":
                nb = 0
                maxWarn = 0
                readErr = 0
                seekErr = 0
                
                for drive in smartAttrs:
                    led[mapping[drive]] = OFF

                    if smartAttrs[drive]['warning'] > MAX_WARNING: 
                        nb += 1    
                        led[mapping[drive]] = BLINK
             
                    if smartAttrs[drive]['warning'] > maxWarn: maxWarn = smartAttrs[drive]['warning'] 
                    readErr  += smartAttrs[drive]['1']
                    seekErr  += smartAttrs[drive]['7']

                oled_writetextaligned(f"{nb} disc ({maxWarn})", stdleftoffset, 36, oledscreenwidth-stdleftoffset, 1, fontwdSml)

                txt = "???"
                if (readErr> 0) and (seekErr == 0): txt = "ReadErr"
                if (readErr==0) and (seekErr == 0): txt = "SeekErr"
                if (readErr >0) and (seekErr >  0): txt = "Read & Seek"                    
                oled_writetextaligned(txt, stdleftoffset, 48, oledscreenwidth-stdleftoffset, 1, fontwdSml)

            if msg == "ERROR":                    
                nb = 0
                errStr = []
                for drive in smartAttrs:
                    led[mapping[drive]] = OFF
                    if smartAttrs[drive]['error'] > 0: 
                        nb += 1
                        led[mapping[drive]] = ON
                        
                    errStr.append(str(smartAttrs[drive]['error']))
                
                oled_writetextaligned(f"{nb} disc", stdleftoffset, 36, oledscreenwidth-stdleftoffset, 1, fontwdSml)
                oled_writetextaligned("/".join(errStr), stdleftoffset, 48, oledscreenwidth-stdleftoffset, 1, fontwdSml)

            '''            
            writeq.put((msg,led))
            needsUpdate = True
            screenjogflag = 1
            curlist=[]
        elif curscreen == "fan":   
            # RAM 
            try:
                oled_loadbg("bgfan")
                speed = setFanSpeed.prevSpeed
                if speed == 0:
                    oled_writetextaligned(f"OFF", stdleftoffset, 24, oledscreenwidth-stdleftoffset, 1, fontwdReg)    
                elif speed == 100:
                    oled_writetextaligned(f"MAX", stdleftoffset, 24, oledscreenwidth-stdleftoffset, 1, fontwdReg)    
                else:
                    oled_writetextaligned(f"Speed", stdleftoffset, 12, oledscreenwidth-stdleftoffset, 1, fontwdReg)
                    oled_writetextaligned(f"{speed}%", stdleftoffset, 32, oledscreenwidth-stdleftoffset, 1, fontwdReg)
                
                needsUpdate = True
            except:
                logError( "Error processing information for fan display")
                needsUpdate = False
                # Next page due to error/no data
                screenjogflag = 1
        elif curscreen == "ram":   
            # RAM 
            try:
                oled_loadbg("bgram")
                ram = getRAMusage()
                oled_writetextaligned(f"{ram['free']}%", stdleftoffset, 8, oledscreenwidth-stdleftoffset, 1, fontwdReg)
                oled_writetextaligned("of", stdleftoffset, 24, oledscreenwidth-stdleftoffset, 1, fontwdReg)
                oled_writetextaligned(f"{ram['sizeGB']}GB", stdleftoffset, 40, oledscreenwidth-stdleftoffset, 1, fontwdReg)
                needsUpdate = True
            except:
                logError( "Error processing information for RAM display")
                needsUpdate = False
                # Next page due to error/no data
                screenjogflag = 1
        elif curscreen == "temp": 
            # Temp
        
            oled_loadbg("bgtemp")
            
            maxcval = sumup['maxTemp']
            mincval = sumup['minTemp']
            cpucval = getCPUusage()['temp']
            

            alltempobj = {"cpu ": cpucval,"hdd":None, " min": mincval, " max": maxcval}

            # Update max C val to CPU Temp if necessary
            if maxcval < cpucval:
                maxcval = cpucval

            displayrowht = 8
            displayrow = 8
            for curdev in alltempobj:
                if alltempobj[curdev] != None :
                    if temperature == "C":
                        # Celsius
                        tmpstr = str(alltempobj[curdev])
                        if len(tmpstr) > 4:
                            tmpstr = tmpstr[0:4]
                    else:
                        # Fahrenheit
                        tmpstr = str(32+9*(alltempobj[curdev])/5)
                        if len(tmpstr) > 5:
                            tmpstr = tmpstr[0:5]

                    oled_writetext(curdev.upper()+": "+ tmpstr+ chr(186) +temperature, stdleftoffset, displayrow, fontwdSml)
                    if (curdev[0] == " "):
                        displayrow = displayrow + displayrowht*1.5
                    else:
                        displayrow = displayrow + displayrowht*2
                else:
                    oled_writetext(curdev.upper(), stdleftoffset, displayrow, fontwdSml)
                    displayrow = displayrow + displayrowht*1.5

                    
            
            # Temperature Bar: 40C is min, 80C is max
            maxht = 21
            barht = int(maxht*(maxcval-40)/40)
            if barht > maxht:
                barht = maxht
            elif barht < 1:
                barht = 1
            oled_drawfilledrectangle(24, 20+(maxht-barht), 3, barht, 2)

            needsUpdate = True
            curlist = []
        elif curscreen == "ip":  
            # IP Address
            try:
                if len(curlist) == 0:
                    curlist = list (getIPlist().items())
            except:
                logError( "Error processing information for IP display")
                curlist = []

            if len(curlist) > 0:
                item = curlist.pop(0)
                oled_loadbg("bgip")
                oled_writetextaligned(item[0], 0, 0, oledscreenwidth, 1, fontwdReg)
                oled_writetextaligned(item[1], 0,16, oledscreenwidth, 1, fontwdReg)
                needsUpdate = True
            else:
                needsUpdate = False
                # Next page due to error/no data
                screenjogflag = 1
        elif curscreen == "disc":
            needsUpdate = True    
        elif curscreen == "reboot":  

            oled_writetext('Click : Reboot', 20, 20, fontwdSml)
            oled_writetext('Twise : Shutdown', 20, 32, fontwdSml)

            devices, sizes   = getDevices()
            names, smartAttrs, sumup = getDevicesSmartsAttr(devices['hd'])
            mapping = getDevicesMapping(devices['hd'])       

            curscreen = "reboot-"
            needsUpdate = True
        elif curscreen == 'clock': # display time            
            oled_loadbg("bgtime")
            # Date and Time HH:MM
            curtime = datetime.datetime.now()
            
            # Month/Day
            outstr = str(curtime.day).strip()
            if len(outstr) < 2:
                outstr = " "+outstr
            outstr = monthlist[curtime.month-1]+" "+outstr
            oled_writetextaligned(outstr, stdleftoffset, 8, oledscreenwidth-stdleftoffset, 1, fontwdReg)

            # Day of Week
            oled_writetextaligned(weekdaynamelist[curtime.weekday()], stdleftoffset, 24, oledscreenwidth-stdleftoffset, 1, fontwdReg)

            # Time
            outstr = str(curtime.minute).strip()
            if len(outstr) < 2:
                outstr = "0"+outstr
            outstr = str(curtime.hour)+":"+outstr
            if len(outstr) < 5:
                outstr = "0"+outstr
            oled_writetextaligned(outstr, stdleftoffset, 40, oledscreenwidth-stdleftoffset, 1, fontwdReg)

            needsUpdate = True
        if needsUpdate == True:
            # Update screen if not screen saver mode
            oled_flushimage(prevscreen != curscreen)
            oled_reset()

            timeoutcounter = 0
            while timeoutcounter<screenjogtime or screenjogtime == 0:
                qdata = ""
                if readq.empty() == False:
                    qdata = readq.get()
                    print(f"qData {qdata}")
                        
                if (qdata == "click") :

                    if (curscreen == "reboot-"):
                        print ("REBOOT")
                        display_defaultimg()
                        time.sleep(1)
                        os.system("reboot -h now")
                        break
                    # Trigger screen switch
                    screenjogflag = 1
                    # Reset Screen Saver
                    screensavermode = False
                    screensaverctr = 0
                    oled_power(True)
                    break
                elif (qdata == "twice") :
                    if (curscreen == "reboot-") :
                        print ("SHUTDOWN")
                        display_defaultimg()
                        time.sleep(1)
                        os.system("shutdown -h now")
                        break                        
                elif (qdata == "press") :                    
                    curscreen = "reboot"
                    break                
                else:
                    screensaverctr = screensaverctr + 1
                    #print(f"screensaverctr : {screensaverctr}, screensaversec : {screensaversec}, screenSave {screensavermode}")
                    if screensaversec <= screensaverctr and screensavermode == False:
                        screensavermode = True
                        oled_power(False)


                    if timeoutcounter == 0:
                        # Use 1 sec sleep get CPU usage
                        cpuusagelist = getCPUusage(1)
                    else:
                        time.sleep(1)

                    timeoutcounter = timeoutcounter + 1
                    if timeoutcounter >= 60 and screensavermode == False:
                        # Refresh data every minute, unless screensaver got triggered
                        screenjogflag = 0
                        break

            

    display_defaultimg()

def display_defaultimg():
    # Load default image
    oled_power(True)
    oled_flushimage()
    oled_reset()
    oled_loadbg("bgdefault")
    oled_flushimage()
    oled_reset()    
    # oled_fill(0)
    


setFanSpeed.prev = 0
if len(sys.argv) > 1:
    cmd = sys.argv[1].upper()
    if cmd == "SHUTDOWN":
        # Signal poweroff
        logInfo( "SHUTDOWN requested via shutdown of command of NAS service")
        setFanOff()
        if OLED_ENABLED == True:
            display_defaultimg()
        
    elif cmd == "FANOFF":
        # Turn off fan
        setFanOff()
        logInfo( "FANOFF requested via fanoff command of the NAS service")
        if OLED_ENABLED == True:
            display_defaultimg()

    elif cmd == "SERVICE":
        display_defaultimg()

        if not (isRoot or not isArmbian):
            print("MUST be executed with root on ArmBian")
            exit()

        # Starts the power button and temperature monitor threads
        try:
            logInfo( f"NAS service version {NAS_VERSION} starting.")

            keyQ = Queue()
            ledQ = Queue()
            t1 = Thread(target = watch_key, args =(keyQ, ))

            t2 = Thread(target = temp_check)
            if OLED_ENABLED == True:
                t3 = Thread(target = display_loop, args =(keyQ, ledQ, ))
                t4 = Thread(target = ledDriver   , args =(ledQ, ))

            t1.start()
            t2.start()        
            if OLED_ENABLED == True:
                t3.start()
                t4.start()

            #ledQ.join()
        except Exception as e:
            print(f"GPIO.cleanup() {e}")

else:
    print( f"Version: {NAS_VERSION}" )
    display_defaultimg()
    time.sleep(3)



