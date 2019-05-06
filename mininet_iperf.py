#!/usr/bin/python3

"""
Mininet iperf test between two hosts
"""

from mininet.net import Mininet
from mininet.topo import SingleSwitchTopo, Topo
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.examples.linuxrouter import LinuxRouter
from pprint import pprint
import time
import subprocess
import csv
import datetime
import multiprocessing


# todo Check where mininet does TC; what should be the limit value
class RTopo(Topo):
    #def __init__(self, **kwargs):
    #global r
    def build(self, **_opts):
        defaultIP = '10.0.1.1/24' 
        r  = self.addNode('r', cls=LinuxRouter, ip=defaultIP)
        h1 = self.addHost('h1', ip='10.0.1.10/24', defaultRoute='via 10.0.1.1')
        h2 = self.addHost('h2', ip='10.0.2.10/24', defaultRoute='via 10.0.2.1')

        self.addLink(h1, r, intfName1 = 'h1-eth', intfName2 = 'r-eth1', params2 = {'ip' : '10.0.1.1/24'})
        self.addLink(h2, r, intfName1 = 'h2-eth', intfName2 = 'r-eth2', params2 = {'ip' : '10.0.2.1/24'})


def iperfTest():
    topo = RTopo()
    net = Mininet(topo=topo)
    net.start()
    h1 = net['h1']
    h2 = net['h2']
    r = net['r']
    
    HZ = 250
    burst = 1e6
    #burst = bw * 1e6 / 8 / HZ
    print(burst)
    
    # Let h1 send data to h2 -- configure tc on r-eth2 (egress to h2)
    IF = 'r-eth2'
    MTU = 1500

    # Configure TC
    r.cmd('tc qdisc add dev ' + IF + ' root handle 1: netem delay ' + str(delay) + 'ms')
    r.cmd('tc qdisc add dev ' + IF + ' parent 1: handle 10: tbf rate ' + str(bw) + 'mbit' + \
                ' burst ' + str(burst) + ' limit ' + str(limit))
   
    # Hmm.. Seems that the latter configured queue will override the previous one, just use previous logic
    # r.cmd('tc qdisc add dev ' + IF + ' root handle 1: tbf rate ' + str(bw) + 'mbit' + \
    #            ' burst ' + str(burst) + ' limit ' + str(1))
    # r.cmd('tc qdisc add dev ' + IF + ' parent 1: handle 10: netem delay ' + str(delay) + 'ms limit ' + str(1000))
    
    linkDelay = delay + rtprop
    #h1.cmd('ethtool -K h1-eth tx off')
    #r.cmd('ethtool -K r-eth1 lro off gro off')
    #r.cmd('ethtool -K r-eth2 lro off gro off')
    #bdp = int(bw * 1e6 / 8 * linkDelay / 1e3)
  
    # Print Network Parameters (BDP/Buffer/QDisc)
    print('\n')
    print(['bdp', convertSize(bdp), 'buffer', convertSize(limit)])             
    print(['cc: ', cc, 'delay', str(linkDelay), 'bw', bw, 'limit', limit, 'burst', burst])
    print(r.cmd('tc qdisc show dev ' + IF))
    
    # Write Log Header
    logfile = open(logname, 'a+')
    print(['cc: ', cc, 'delay', str(linkDelay), 'bw', bw, 'limit', limit, 'burst', burst], file=logfile)
    
    # TODO: before the experiment start, initiate a process to track the backlog usage
    # sp = multiprocessing.Process(target=sampleTBFBacklog, args=(r, IF, logfile,))
    # sp.start()
   
    # Ping the network to see if any errors
    # print(h1.cmd('ping -c5', h2.IP()))

    iperf_server = h1.cmd('iperf3 -s -p 5001&')
    iperf_client = h2.cmd('iperf3 -c 10.0.1.10 -t ' + str(t) + ' -i 1 -p 5001 -R')
    
    h1.cmd('pkill iperf3')
    h2.cmd('pkill iperf3')
    # sp.terminate()

    # Save the experimental logs to file
    print(iperf_client, file=logfile)
    logfile.close()
    
    retr = int(iperf_client.splitlines()[-4].split()[8])
    goodput = float(iperf_client.splitlines()[-3].split()[-3])
    unit = iperf_client.splitlines()[-3].split()[-2]
    
    if unit == "Gbits/sec":
        goodput *= 1e9
    elif unit == "Mbits/sec":
        goodput *= 1e6
    elif unit == "Kbits/sec":
        goodput *= 1e3
    elif unit == "bits/sec":
        pass
   
    if goodput > 0:
        loss = retr / (goodput * t / 8 / MTU) * 100
    else:
        loss = 100

    record = [cc, linkDelay, bw, limit, burst, retr, convertSize(bdp), convertSize(limit), loss, goodput]
    
    csvfile = open(csvname, 'a+')
    writer = csv.writer(csvfile)
    writer.writerow(record)
    csvfile.close()
    
    net.stop()
    print('Success!' + ' -- ' + str(record))


def sampleTBFBacklog(r, IF, logfile):
    st = time.time()
    cur = time.time()
    intv = 0.01

    while True:
        out = r.cmd("tc -p -s -d qdisc show dev " + IF + " | grep backlog | awk '{print $2}'")
        out = out.replace('b', '').splitlines()
        
        line = ','.join([str(round(cur - st, 3))] + out)
        print(line, file=logfile)
        time.sleep(intv)
        cur = time.time()
        

def sampleRTT(pairs, logfile):
    st = time.time()
    cur = time.time()
    intv = 0.01
   
    node = {}
    num = len(pairs)
    for p in pairs:
        node[p[0]] = p[1]

    while True:
        bbrout = node['bbr'].cmd('ss -tin | grep bbr').split()        
        cubicout = node['cubic'].cmd('ss -tin | grep cubic').split()        
        bbrRTT, cubicRTT = -1, -1

        for item in bbrout:
            if 'rtt:' in item and '/' in item:
                bbrRTT = float(item.split('/')[0][4:])
        
        for item in cubicout:
            if 'rtt:' in item and '/' in item:
                cubicRTT = float(item.split('/')[0][4:])
        
        if bbrRTT > 0 and cubicRTT > 0:
            line = ','.join([str(round(cur - st, 3)), str(bbrRTT), str(cubicRTT)])
            print(line, file=logfile)

        time.sleep(intv)
        cur = time.time()


def convertSize(num):
    cnt = 0
    while num >= 1000:
        num /= 1000
        cnt += 3
    
    unit = [''] * 9
    unit[0], unit[3], unit[6]  = 'B', 'KB', 'MB'
    
    return str(int(num)) + unit[cnt]


if __name__ == '__main__':
    
    DEBUG = False
    # DEBUG = True
    repNum = 10

    for expID in range(repNum):
        _start = time.time()
        
        ccs = ['bbr', 'cubic'] # 2 values        
        delays = [5, 10, 25, 50, 75, 100, 150, 200] # 8 values
        bws = [10, 20, 50, 100, 250, 500, 750, 1000] # 8 values
        limits = [1e5, 1e6, 10e6, 20e6, 50e6] # 5 values
        t = 60
        to = 10
        rtprop = 0

        if DEBUG:
            ccs = ['bbr']
            delays = [200] # 5 values
            bws = [100, 1e3] # 5 values
            limits = [1e6, 10e6, 20e6] # 5 values
            t = 10
 
        '''
        In total, we have 2*8*8*5 = 640 combinations. Each exp takes 30s -> 320min=5hrs.
        '''
        d = datetime.datetime.now()

        # Create CSV File
        csvname = "tbf-exp-" + "{:%y%m%d_%H%M%S}".format(d) + ".csv"
        csvfile = open(csvname, 'a+')
        writer = csv.writer(csvfile)
        writer.writerow(['CC', 'Delay', 'BW', 'Limit', 'Burst', 'Retr', 'BDP', 'Buffer', 'Loss', 'Goodput'])
        csvfile.close()

        # Create Log File
        logname = "tbf-exp-" + "{:%y%m%d_%H%M%S}".format(d) + ".log"
        logfile = open(logname, 'a+')
        logfile.close()
        
        # Record failed tests
        deList = set()
        allcnt, errcnt = 0, 0

        # Main Loop
        for cc in ccs:
            print("Switching congestion control to: " + cc)
            subprocess.run("sysctl -w net.ipv4.tcp_congestion_control=" + cc, shell=True)
            for bw in bws:
                for delay in delays:
                    # Calculate BDP
                    bdp = int(bw * 1e6 / 8 * delay / 1e3)
                    for limit in limits:
                        allcnt += 1
                        print('\n[' + str(allcnt) + ',' + str(errcnt) + '] - deList: ' + str(deList))
                        
                        def expProcess():
                            p = multiprocessing.Process(target=iperfTest)
                            # Timing the iperf process
                            start = time.time()
                            p.start()
                            p.join(t + to)
                            end = time.time()
                            print('Elaspe time: ' + str(end - start) + 's')
                            return p
                        
                        p = expProcess()
                        
                        # Rerun if test failed
                        while p.is_alive():
                            print('Experiment failed... Terminating the process!')
                            p.terminate()
                            deList.add('-'.join([str(bw), str(delay), str(limit), str(bdp)]))
                            errcnt += 1

                            print('Repeat experiment...')
                            p = expProcess() 

        _end = time.time()
        print('Programming Running Time: ' + str(_end - _start) + 's')
