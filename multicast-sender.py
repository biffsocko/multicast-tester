#!/usr/bin/env python3
##################################################
# TR Murphy
# multicast-sender.py
#
# test program for testing multicast connections
# between servers.
#
# This sends a stream of multicast data to a group and
# port number specified at the command line.
#
# the data is taken from /dev/zero; in Linux this is
# just a stream of zero's that go on forever.
#
# usage:
#  ./multicast-sender.py 239.0.0.1 1234
#
# user@server1:~$ ./multicast-sender.py --help
# usage: multicast-sender.py [-h] group port
#
# Send multicast data from /dev/zero
#
# positional arguments:
#   group       Multicast group name
#   port        Port number
#
# optional arguments:
#   -h, --help  show this help message and exit
##################################################
import socket
import argparse

def send_multicast_data(group, port):
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    # Enable multicast TTL
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    # Set the multicast group and port
    group_address = (group, port)

    # Open /dev/zero for reading
    with open('/dev/zero', 'rb') as zero_file:
        # Continuously read from /dev/zero and send multicast data
        while True:
            data = zero_file.read(1024)  # Read 1024 bytes from /dev/zero

            # Send the data to the multicast group
            sock.sendto(data, group_address)

####################################
# MAIN
####################################
# Parse the command-line arguments
parser = argparse.ArgumentParser(description='Send multicast data from /dev/zero')
parser.add_argument('group', help='Multicast group name')
parser.add_argument('port', type=int, help='Port number')
args = parser.parse_args()

# Call the function to send multicast data
send_multicast_data(args.group, args.port)
exit(0)
