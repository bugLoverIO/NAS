import os
import time
import socket
import psutil
import math
from datetime import datetime, timedelta
from pathlib import Path

isArmbian = False

def _readSytem(cmd, file, isProcess):
    def stringProcess(inString):
        out = inString.replace('\t', ' ')
        out = out.strip()
        while out.find("  ") >= 0:
            out = out.replace("  ", " ")
        out = out.split(" ")
        return out
    
    try:
        if isArmbian:
            if isProcess:
                command = os.popen(cmd)            
                out = command.read()
                command.close()
            else:
                command = os.open(cmd)            
                out = command.read()
                command.close()
        else:
            command = open(file, "r")
            out = command.read()
            command.close()
    except IOError:
        if isArmbian:
            print(f"ERROR calling {cmd} ")
        else: 
            print(f"ERROR reading {file} ")

        return None

    out = [l for l in out.split("\n") if l]
    
    output = []
    for i in out:
        output.append(stringProcess(i))

    return output


def checkPrivilege():
    """
    Determine if the user can properly execute the script.  Must have sudo or be root
    """
    isRoot = True
    global isArmbian
    if not ('SUDO_UID' in os.environ ) and os.geteuid() != 0:
        isRoot = False
    
    command = os.popen("uname -s")
    tmp = command.read().replace("\n","")
    command.close()

    if (tmp == "Linux"):
        isArmbian = True

    return (isRoot, isArmbian)


# Devices {'hd': ['sda', 'sdb', 'sdc', 'sdd', 'sde'], 'mnt': ['md0', 'mmcblk1p1']}
# Sizes   {'sda': '1.0TB', 'sdb': '1.0TB', 'sdc': '1.0TB', 'sdd': '1.0TB', 'sde': '1.0TB', 'md0': '4.0TB', 'mmcblk1p1': '61.2GB'}
def getDevices():
    hd   = []
    mnt  = []
    size = {}

    def kbstr(kbval, wholenumbers = True):
        remainder = 0
        suffixidx = 0
        suffixlist = ["KB", "MB", "GB", "TB"]
        kbval = int(kbval / 1000)
        while kbval > 999 and suffixidx < len(suffixlist):
            remainder = kbval % 1000
            kbval  = int(kbval / 1000)
            suffixidx = suffixidx + 1

        return str(kbval)+"."+str(remainder)[0:1] + suffixlist[suffixidx]
        
    lines  = _readSytem("lsblk -lb", 
                        "probe/lsblk-l.txt", 
                        True)

    for line in lines[1:]:
        if (len(line) == 7):
            mnt.append(line[0]) 
            size[line[0]]=kbstr(int(line[3]))
        else:
            if line[0][0:2] == "sd" or line[0][0:2] == "hd":    
                hd.append(line[0]) 
                size[line[0]]=kbstr(int(line[3]))
        
    return ({'hd':hd,'mnt':mnt}, size)

#  Smart Name  {'1': 'Raw_Read_Error_Rate', '7': 'Seek_Error_Rate', '194': 'Temperature_Celsius', '196': 'Reallocated_Event_Count', '197': 'Current_Pending_Sector', '198': 'Offline_Uncorrectable'}
#  Smart Attrs {'sda': {'1': 0, '7': 0, '194': 35, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}, 'sdb': {'1': 10, '7': 0, '194': 31, '196': 0, '197': 0, '198': 0, 'warning': 10, 'error': 0}, 'sdc': {'1': 0, '7': 0, '194': 31, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}, 'sdd': {'1': 0, '7': 0, '194': 29, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}, 'sde': {'1': 0, '7': 0, '194': 30, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}}
#  Smart Sumup {'maxTemp': 35, 'warning': 10, 'error': 0}
def getDevicesSmartsAttr(devices):
    names = {}
    values = {}
    sumup = {}
    sumup['maxTemp'] = 0
    sumup['minTemp'] = 200
    sumup['warning'] = 0
    sumup['error'] = 0


    for device in devices:
        values[device] = {}

        lines  = _readSytem(f"/usr/sbin/smartctl -d sat -A /dev/{device}", 
                            f"probe/{device}.smart.txt", 
                            True)
        
        for line in lines[5:]:
            if line[0] in ["1", "7", "194", "190", "196", "197", "198"]:
                names[line[0]] = line[1]           
                values[device][line[0]] = int(line[9]) 
                                            
        values[device]['warning'] = values[device]['1']+values[device]['7']
        values[device]['error']   = values[device]['196']+values[device]['197']+values[device]['198']

        if values[device]['194'] > sumup['maxTemp']: 
            sumup['maxTemp']= values[device]['194']

        if values[device]['194'] < sumup['minTemp']: 
            sumup['minTemp']= values[device]['194']

        sumup['warning'] += values[device]['warning'] 
        sumup['error']   += values[device]['error'] 

    
    return (names, values, sumup)                

#   Standby {'sda': False, 'sdb': True, 'sdc': True, 'sdd': True, 'sde': True}
def getDevicesStandby(devices):
    values = {}

    for device in devices:
        values[device] = {}

        lines  = _readSytem(f"/usr/sbin/smartctl -d sat -n standby,0 /dev/{device}", 
                    f"probe/{device}.active.txt",
                    True)
        
        line = lines[2]

        values[device] = line[3] == "STANDBY"

    return (values)                

#   Mapping  {'sda': ('ata', 1), 'sdb': ('ata', 2), 'sdc': ('ata', 3), 'sdd': ('ata', 4), 'sde': ('ata', 5)}
def getDevicesMapping(devices): #return a disc by device with its ATA mapping
    mapping = {}
    lines = []
    
    for dev in devices: 
        line = _readSytem(f"/usr/bin/udevadm info -q path -p /sys/block/{dev}", 
                f"probe/udevadm.txt",
                True)
        
        if len(line) == 1: 
            lines.append(line[0])
        else: 
            lines = line
            break

    for line in lines:
        line = line[0].split("/")
        mapping[line[12]] = (line[7][:-1], int(line[7][-1:]))
    
    return mapping

#   Activity {'md0': {'read': 26914, 'write': 224}, 'mmcblk1p1': {'read': 956173, 'write': 7278577}}
def getDeviceActivty(devices ):

    output = {}
    
    for device in devices:
        file = f"/sys/block/{device}/stat"
        if not os.path.exists(file):
            file = f"/sys/block/{device[:-2]}/stat"

        lines  = _readSytem(f"cat {file}", 
                            f"probe/{device}.stat.txt", 
                            True)
        line = lines[0]
        if len(line) >= 11:
            output[device] = {"read":int(line[2]), "write":int(line[6])}   

    return output

#  Usage    {'mmcblk1p1': {'free': '58G', 'total': '61G', 'percent': 4}, 'md0': {'free': '3.8T', 'total': '4.0T', 'percent': 1}}
def getDeviceUsage(devices): 

    output = {}
    
    lines  = _readSytem(f"df -H", 
                    f"probe/df.txt", 
                    True)

    for line in lines[1:]:
        tmpidx = line[0].rfind("/")
        if tmpidx >= 0:
            curdev = line[0][tmpidx+1:]
        else:
            continue
        
        if curdev not in devices:          
            continue        
        
        output[curdev] = {}
        output[curdev]["free"]         = line[3].replace(",",".")
        output[curdev]["total"]        = line[1].replace(",",".")
        output[curdev]["percent"]      = int(line[4][0:-1])

    return output

#  Summary  {'md0': {'type': 'raid5', 'active': 'active', 'devices': ['sde', 'sdd', 'sdb', 'sdc', 'sda'], 'disc': (5, 5, 'UUUUU'), 'status': 'clean', 'recovery': None}}
def getRAID():           # List RAID and details (do no spin up drive )
    hddList = []
    output = {}

    lines  = _readSytem(f"cat /proc/mdstat", 
                        f"probe/mdstat.txt", 
                        True)
    
    # Check first line, and drop it
    if lines[0][0] != "Personalities":
        print("ERROR : processing /proc/mdstat")
        return None
    lines = lines[1:]

    # process then next lines
    
    # process first line
    devName  = lines[0][0]
    raidType = lines[0][3]
    active   = lines[0][2]
        
    hddctr = 4
    while hddctr < len(lines[0]):
        tmpDevice = lines[0][hddctr]
        tmpidx = tmpDevice.find("[")
        if tmpidx >= 0:
            tmpId = int(tmpDevice[tmpidx+1:-1])
            tmpDevice = tmpDevice[0:tmpidx]
        hddList.append(tmpDevice)
        hddctr = hddctr + 1

    # process second line
    nbDiscTotal = int(lines[1][10][1:-1].split("/")[0])
    nbDiscInUsed = int(lines[1][10][1:-1].split("/")[1])
    disc = lines[1][11][1:-1]

    # process third line
    recovery = None
    if len(lines[2]) > 1:
        status = None
        if lines[2][0] == "bitmap:": 
            if nbDiscTotal == nbDiscInUsed:
                status = 'clean'
            elif nbDiscTotal == nbDiscInUsed+1:
                status = 'degraded'
            else:
                status = 'error'

        if lines[2][1] == "recovery": 
            status = 'recovering'
            percentage = float(lines[2][3][:-1])
            duration = float(lines[2][5].split("=")[1][:-3])
            speed =  int(lines[2][6].split("=")[1][:-5])
            recovery = {'percentage':percentage,'duration':duration, 'speed':speed}
        

    output[devName] = { 'type'      : raidType, 
                        'active'    : active, 
                        'devices'   : hddList, 
                        'disc'      : (nbDiscTotal,nbDiscInUsed,disc), 
                        'status'    : status,
                        'recovery'  : recovery}

    return output

#  CPU    {'load': 83, 'temp': 43.888, 'loadByCPU': [100, 0, 100, 100, 100, 100]}
def getCPUusage(sleepsec = 1):

    def getCPUtemp():

        lines  = _readSytem(f"cat /sys/class/thermal/thermal_zone0/temp", 
                            f"probe/temp.txt", 
                            True)         

        return float(int(lines[0][0])/1000)

    def getCPUusageSnapshot():
        
        output = {}     
        cpuCtr = 0

        # user, nice, system, idle, iowait, irc, softirq, steal, guest, guest nice
        lines  = _readSytem(f"cat /proc/stat", 
                            f"probe/stat.txt", 
                            True)            

        for line in lines:
            if len(line) < 3:
                cpuCtr = cpuCtr +1
                continue

            if line[0][:3] == "cpu":
                idle = 0
                total = 0
                colctr = 1
                while colctr < len(line):
                    curval = int(line[colctr])
                    if colctr == 4 or colctr == 5:
                        idle = idle + curval
                    total = total + curval
                    colctr = colctr + 1
                if total > 0:
                    output[line[0]] = {"total": total, "idle": idle}
            cpuCtr = cpuCtr +1

        return output
    
    def getLoad (cpuName, A, B):
        if A[cpuName]["total"] == B[cpuName]["total"]:
            return 0
        else:
            total = B[cpuName]["total"]-A[cpuName]["total"]
            idle = B[cpuName]["idle"]-A[cpuName]["idle"]
            return int(100*(total-idle)/(total))   

    output = {}
    curUsageA = getCPUusageSnapshot()
    time.sleep(sleepsec)
    curUsageB = getCPUusageSnapshot()

    output['load'] = getLoad('cpu',curUsageA, curUsageB )
    output['temp'] = getCPUtemp()
    output['loadByCPU'] = []

    for cpuName in curUsageA:
        if cpuName == 'cpu': continue
        output['loadByCPU'].append(getLoad(cpuName,curUsageA, curUsageB ))

    return output

#  RAM    {'free': 89, 'SizeGB': 4}
def getRAMusage():
    totalRam = 0
    totalFree = 0
    
    lines  = _readSytem(f"cat /proc/meminfo", 
                        f"probe/meminfo.txt", 
                        True)
     

    for line in lines:
        if line[0] == "MemTotal:":
            totalRam = int(line[1])
        elif line[0] == "MemFree:":
            totalFree = totalFree + int(line[1])
        elif line[0] == "Buffers:":
            totalFree = totalFree + int(line[1])
        elif line[0] == "Cached:":
            totalFree = totalFree + int(line[1])

    if totalRam == 0:
        return {'free':0, 'sizeGB':0}
    
    return {'free':int(100*totalFree/totalRam), 'sizeGB':(totalRam+512*1024)>>20}

#   IP     192.168.0.111
def getIP():
    ipaddr = ""
    st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: 
        # Connect to nonexistent device
        st.connect(('254.255.255.255', 1))
        ipaddr = st.getsockname()[0]
    except Exception:
        ipaddr = 'N/A'
    finally:
        st.close()
    return ipaddr

#   List   [('eth0', '192.168.0.111')]
def getIPlist():
    output = {}
    for interface, snics in psutil.net_if_addrs().items():
        if not interface.startswith("lo") and not interface.startswith("br"):
            for snic in snics:
                if snic.family == socket.AF_INET :
                    output[interface] = snic.address
                    
    return output

def kbstr(kbval, wholenumbers = True):
        remainder = 0
        suffixidx = 0
        suffixlist = ["KB", "MB", "GB", "TB"]
        while kbval > 1023 and suffixidx < len(suffixlist):
            remainder = kbval & 1023
            kbval  = kbval >> 10
            suffixidx = suffixidx + 1

        #return str(kbval)+"."+str(remainder) + suffixlist[suffixidx]
        remainderstr = ""
        if kbval < 100 and wholenumbers == False:
            remainder = int((remainder+50)/100)
            if remainder > 0:
                remainderstr = "."+str(remainder)
        elif remainder >= 500:
            kbval = kbval + 1
        return str(kbval)+remainderstr + suffixlist[suffixidx]


def get_size(bytes, suffix="B"):
     """
     Scale bytes to its proper format- KB, MB, GB, TB and PB
     """
     factor = 1024
     for unit in ["", "K", "M", "G", "T", "P"]:
         if bytes < factor:
             return f"{bytes:.2f}{unit}{suffix}"
         bytes /= factor
 


if __name__ == "__main__":
    '''
    CHECK isRoot:False, isArmbian False
    DEVICES
        Devices {'hd': ['sda', 'sdb', 'sdc', 'sdd', 'sde'], 'mnt': ['md0', 'mmcblk1p1']}
        Sizes   {'sda': '1.0TB', 'sdb': '1.0TB', 'sdc': '1.0TB', 'sdd': '1.0TB', 'sde': '1.0TB', 'md0': '4.0TB', 'mmcblk1p1': '61.2GB'}
        Smarts Attributes
            Name  {'1': 'Raw_Read_Error_Rate', '7': 'Seek_Error_Rate', '194': 'Temperature_Celsius', '196': 'Reallocated_Event_Count', '197': 'Current_Pending_Sector', '198': 'Offline_Uncorrectable'}
            Attrs {'sda': {'1': 0, '7': 0, '194': 41, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}, 'sdb': {'1': 10, '7': 0, '194': 41, '196': 0, '197': 0, '198': 0, 'warning': 10, 'error': 0}, 'sdc': {'1': 0, '7': 0, '194': 42, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}, 'sdd': {'1': 0, '7': 0, '194': 44, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}, 'sde': {'1': 0, '7': 0, '194': 44, '196': 0, '197': 0, '198': 0, 'warning': 0, 'error': 0}}
            Sumup {'maxTemp': 44, 'minTemp': 41, 'warning': 10, 'error': 0}
        Mapping  {'sda': ('ata', 1), 'sdb': ('ata', 2), 'sdc': ('ata', 3), 'sdd': ('ata', 4), 'sde': ('ata', 5)}
        Standby  {'sda': False, 'sdb': False, 'sdc': False, 'sdd': False, 'sde': False}
        Activity {'md0': {'readsector': 25986, 'writesector': 64}, 'mmcblk1p1': {'readsector': 923863, 'writesector': 1819986}}
        Usage    {'mmcblk1p1': {'free': '58G', 'total': '61G', 'percent': 4}, 'md0': {'free': '3.8T', 'total': '4.0T', 'percent': 1}}

    RAID
        Summary {'md0': {'type': 'raid5', 'active': 'active', 'devices': ['sde', 'sdd', 'sdb', 'sda', 'sdc'], 'disc': (5, 5, 'UUUUU'), 'status': 'clean', 'recovery': None}}

    Chip
        CPU    {'load': 9, 'temp': 32.777, 'loadByCPU': [2, 2, 6, 13, 28, 2]}
        RAM    {'free': 89, 'sizeGB': 4}

    IP
        IP     192.168.0.111
        List   {'eth0': '192.168.0.111'}
    '''
    isRoot, isArmbian = checkPrivilege()
    print (f"CHECK isRoot:{isRoot}, isArmbian {isArmbian}")
    
    if (isRoot or not isArmbian):
        devices,sizes = getDevices()
        names, smartAttrs, sumup = getDevicesSmartsAttr(devices['hd'])
        mapping       = getDevicesMapping(devices['hd'])
        standby       = getDevicesStandby(devices['hd'])
        raid          = getRAID()
        activity      = getDeviceActivty(devices['mnt'])
        usage         = getDeviceUsage(devices['mnt'])
        ip            = getIP()
        ipList        = getIPlist()
        cpuUsage      = getCPUusage()
        ramUsage      = getRAMusage()

        print("DEVICES")
        print(f"  Devices {devices}")
        print(f"  Sizes   {sizes}")
        print(f"  Smarts Attributes")
        print(f"    Name  {names}")
        print(f"    Attrs {smartAttrs}")
        print(f"    Sumup {sumup}")
        print(f"  Mapping  {mapping}")
        print(f"  Standby  {standby}")
        print(f"  Activity {activity}")
        print(f"  Usage    {usage}")
        print("\nRAID")
        print(f"  Summary {raid}")
        print("\nChip")
        print (f"  CPU    {cpuUsage}")
        print (f"  RAM    {ramUsage}")
        print("\nIP")
        print (f"  IP     {ip}")
        print (f"  List   {ipList}")
    else:
        print("Must be executed with ROOT privilege")



