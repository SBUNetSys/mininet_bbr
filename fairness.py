'''
router topology example for TCP competions.
   
   h1----+
         |
         r ---- h3
         |
   h2----+

'''

from mininet.net import Mininet
from mininet.cli import CLI
from mininet.examples.linuxrouter import LinuxRouter
from mininet.link import TCLink
from mininet.topo import Topo
from mininet.log import setLogLevel, info
from mininet_iperf_new import convertSize, sampleTBFBacklog, sampleRTT
import multiprocessing
import subprocess
import time
import asyncio
import os


# TODO Buffer usage/Multiple values

class RTopo(Topo):
    def build(self, **_opts):     # special names?
        defaultIP = '10.0.1.1/24'  # IP address for r0-eth1
        r  = self.addNode( 'r', cls=LinuxRouter, ip=defaultIP)
        h1 = self.addHost( 'h1', ip='10.0.1.10/24', defaultRoute='via 10.0.1.1' )
        h2 = self.addHost( 'h2', ip='10.0.2.10/24', defaultRoute='via 10.0.2.1' )
        h3 = self.addHost( 'h3', ip='10.0.3.10/24', defaultRoute='via 10.0.3.1' )
 
        self.addLink(h1, r, intfName1 = 'h1-eth', intfName2 = 'r-eth1', params2 = {'ip' : '10.0.1.1/24'})
        self.addLink(h2, r, intfName1 = 'h2-eth', intfName2 = 'r-eth2', params2 = {'ip' : '10.0.2.1/24'})
        self.addLink(h3, r, intfName1 = 'h3-eth', intfName2 = 'r-eth3', params2 = {'ip' : '10.0.3.1/24'})
        

def main():
    
    rtopo = RTopo()
    net = Mininet(topo = rtopo)

    net.start()
    
    r = net['r']
    IF = 'r-eth3'
    
    r.cmd('tc qdisc add dev ' + IF + ' root handle 1: netem delay ' + str(delay) + 'ms')
    r.cmd('tc qdisc add dev ' + IF + ' parent 1: handle 10: tbf rate ' + str(bw) + 'mbit' + \
                ' burst ' + str(burst) + ' limit ' + str(limit))

    h1 = net['h1']
    h2 = net['h2']
    h3 = net['h3']
   
    h3Log1 = expName + '-h3_1.log'
    h3Log2 = expName + '-h3_2.log'
    h1Log = expName + '-h1.log'
    h2Log = expName + '-h2.log'

    print('Starting receiver h3..')  
    h3.cmd('iperf3 -s -p 5001 | tee ' + h3Log1 + ' &')
    h3.cmd('iperf3 -s -p 5002 | tee ' + h3Log2 + ' &')
    
    # Start RTT sampling
    proc = multiprocessing.Process(target=sampleRTT, args=([('bbr', h1), ('cubic', h2)], logFile))
    proc.start()

    print('Starting senders h1/h2..') 
    h1.cmd('iperf3 -c 10.0.3.10 -t ' + str(duration) + ' -i 1 -p 5001 -C ' + cc1 + ' | tee ' + h1Log + ' &')    
    h2.cmd('iperf3 -c 10.0.3.10 -t ' + str(duration) + ' -i 1 -p 5002 -C ' + cc2 + ' | tee ' + h2Log + ' &')  

    time.sleep(duration + 5)
    proc.terminate()

    net.stop()

    # Process the results    
    # Get h1's goodput from h3Log1; h2's goodput from h3Log2; h1's retr from h1Log; h2's retr from h2Log
    with open(h3Log1, 'r') as file:
        data = file.read()
        h1_goodput = float(data.splitlines()[-1].split()[-3])
        unit = data.splitlines()[-1].split()[-2]

    with open(h3Log2, 'r') as file:
        data = file.read()
        h2_goodput = float(data.splitlines()[-1].split()[-3])
        unit = data.splitlines()[-1].split()[-2]

    with open(h1Log, 'r') as file:
        data = file.read()
        h1_retr = data.splitlines()[-4].split()[8]

    with open(h2Log, 'r') as file:
        data = file.read()
        h2_retr = data.splitlines()[-4].split()[8]

    record = [convertSize(limit), h1_goodput, h2_goodput, h1_retr, h2_retr]
    record = ','.join(list(map(str, record)))
    print('\n' + record, file=logFile)
    

if __name__ == "__main__":
    
    ccPairs = [('bbr', 'cubic')]
    limits = [1e4, 1e5, 1e6, 5e6, 1e7, 5e7, 1e8]
    bw, delay, burst = 1000, 20, 1e6
    duration = 60
    for run in range(1):
        for cc1, cc2 in ccPairs:
            logName = '-'.join([cc1, cc2]) + '.log' + str(run)
            logFile = open(logName, 'w+')

            for limit in limits:
                expName = '-'.join([cc1, cc2, str(convertSize(limit))])
                print('\n' + expName)

                main()

            logFile.close()
