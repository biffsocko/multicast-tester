#!/usr/bin/env python3
###################################################################################################
# TR Murphy
# multicast-listen.py
#
# usage:
# ./multicast-listen.py [multicast group] [multicast port] [local interface ip address]
###################################################################################################

import socket
import sys

BYTES = 10240


##################################
# joinMcast
##################################
def joinMcast(mcast_addr, port, if_ip):
    # create a UDP socket
    mcastsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # allow other sockets to bind this port too
    mcastsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # join the multicast group on the interface specified
    mcastsock.setsockopt(
        socket.SOL_IP,
        socket.IP_ADD_MEMBERSHIP,
        socket.inet_aton(mcast_addr) + socket.inet_aton(if_ip),
    )

    # bind the socket to start getting data into your socket
    mcastsock.bind((mcast_addr, port))

    return mcastsock


##################################
# MAIN
##################################
num_args = len(sys.argv)
print(num_args)
script_name = sys.argv[0]
print(f"Script name: {script_name}")

usage = script_name + " [multicast group] [multicast port] [local interface ip address]"

if num_args != 4:
    print(usage)
    sys.exit(1)
else:
    MCAST_GRP = sys.argv[1]
    MCAST_PORT = int(sys.argv[2])
    INTERFACEIP = sys.argv[3]


sock = joinMcast(MCAST_GRP, MCAST_PORT, INTERFACEIP)
sock.settimeout(10)
try:
    print(f"printing first {BYTES} bytes: ")
    data = sock.recv(BYTES)
except OSError:
    print(
        "failed reading group "
        + MCAST_GRP
        + " on port "
        + str(MCAST_PORT)
        + " and interface: "
        + INTERFACEIP
    )
    sys.exit(1)

finally:
    sock.close()

if not data:
    print("no bytes received")
    sys.exit(1)

print(data)
sys.exit(0)
